from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parent
PDF_SOURCE_DIR = ROOT / "기출문제"
OUTPUT = ROOT / "questions.json"
CROP_OUTPUT_DIR = ROOT / "assets" / "question-crops"
CROP_OUTPUT_PREFIX = "assets/question-crops"
CROP_ZOOM = 2
CROP_MARGIN_X = 42
CROP_MARGIN_TOP = 8
CROP_MARGIN_BOTTOM = 1
ANSWER_SKIP_HEIGHT = 24


@dataclass(frozen=True)
class PdfSpec:
    filename: str
    title: str
    slug: str
    expected_count: int


PDFS = [
    PdfSpec("정보처리기사실기_01_키워드찾기130문제.pdf", "키워드찾기", "keyword", 130),
    PdfSpec("정보처리기사실기_02_SQL17문제.pdf", "SQL", "sql", 17),
    PdfSpec("정보처리기사실기_03_코드-제어문14문제.pdf", "코드-제어문", "code-control", 14),
    PdfSpec("정보처리기사실기_04_코드-포인터5문제.pdf", "코드-포인터", "code-pointer", 5),
    PdfSpec("정보처리기사실기_05_코드-구조체3문제.pdf", "코드-구조체", "code-struct", 3),
    PdfSpec("정보처리기사실기_06_코드-사용자정의함수9문제.pdf", "코드-사용자정의함수", "code-function", 9),
    PdfSpec("정보처리기사실기_07_코드-JAVA활용9문제.pdf", "코드-JAVA활용", "code-java", 9),
    PdfSpec("정보처리기사실기_08_코드-Python활용6문제.pdf", "코드-Python활용", "code-python", 6),
]


@dataclass(frozen=True)
class TextAnchor:
    number: int
    page_index: int
    y: float
    coord: float


@dataclass(frozen=True)
class AnswerAnchor:
    page_index: int
    y: float
    coord: float


def linear_coord(page_index: int, y: float) -> float:
    return page_index * 10000 + y


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("：", ":")
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized.strip()


def extract_pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        pages = [page.get_text("text", sort=True) for page in doc]
    return normalize_text("\n".join(pages))


def pdf_path(spec: PdfSpec) -> Path:
    return PDF_SOURCE_DIR / spec.filename


def iter_text_lines(page: fitz.Page) -> list[tuple[float, str]]:
    lines: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
    for x0, y0, _x1, _y1, word, block_no, line_no, _word_no in page.get_text("words", sort=True):
        lines.setdefault((block_no, line_no), []).append((x0, y0, word))

    result: list[tuple[float, str]] = []
    for items in lines.values():
        items.sort(key=lambda item: item[0])
        y = min(item[1] for item in items)
        text = " ".join(item[2] for item in items).strip()
        if text:
            result.append((y, text))
    return sorted(result, key=lambda item: item[0])


def collect_question_anchors(
    doc: fitz.Document, expected_count: int, filename: str
) -> tuple[list[TextAnchor], list[AnswerAnchor], list[AnswerAnchor]]:
    candidates: list[TextAnchor] = []
    answers: list[AnswerAnchor] = []
    explanations: list[AnswerAnchor] = []

    for page_index, page in enumerate(doc):
        for y, text in iter_text_lines(page):
            question_match = re.match(r"^(\d+)\.(?:\s+|$)", text)
            if question_match:
                candidates.append(
                    TextAnchor(
                        number=int(question_match.group(1)),
                        page_index=page_index,
                        y=y,
                        coord=linear_coord(page_index, y),
                    )
                )

            if re.match(r"^답\s*(?::|$)", text):
                answers.append(AnswerAnchor(page_index, y, linear_coord(page_index, y)))

            if re.match(r"^(?:배열\s*<field>\s+)?배열\s*<mines>$", text):
                answers.append(AnswerAnchor(page_index, y, linear_coord(page_index, y)))

            if re.match(r"^(?:\[\s*해설\s*\]|해설)$", text):
                explanations.append(AnswerAnchor(page_index, y, linear_coord(page_index, y)))

    candidates.sort(key=lambda anchor: anchor.coord)
    answers.sort(key=lambda anchor: anchor.coord)
    explanations.sort(key=lambda anchor: anchor.coord)

    starts: list[TextAnchor] = []
    cursor = -1.0
    for number in range(1, expected_count + 1):
        match = next(
            (anchor for anchor in candidates if anchor.number == number and anchor.coord > cursor),
            None,
        )
        if not match:
            raise ValueError(f"{filename}: {number}번 문제의 PDF 좌표를 찾지 못했습니다.")
        starts.append(match)
        cursor = match.coord

    return starts, answers, explanations


def reset_crop_output_dir() -> None:
    if CROP_OUTPUT_DIR.exists():
        shutil.rmtree(CROP_OUTPUT_DIR)
    CROP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def crop_between(
    doc: fitz.Document,
    spec: PdfSpec,
    question_number: int,
    crop_index: int,
    start_page_index: int,
    start_y: float,
    end_page_index: int,
    end_y: float,
) -> list[dict[str, object]]:
    crops: list[dict[str, object]] = []

    for page_index in range(start_page_index, end_page_index + 1):
        page = doc[page_index]
        top = start_y if page_index == start_page_index else 0
        bottom = end_y if page_index == end_page_index else page.rect.height
        top = max(0, top)
        bottom = min(page.rect.height, bottom)
        if bottom - top < 24:
            continue

        rect = fitz.Rect(CROP_MARGIN_X, top, page.rect.width - CROP_MARGIN_X, bottom)
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(CROP_ZOOM, CROP_ZOOM),
            clip=rect,
            alpha=False,
        )
        filename = f"{spec.slug}-{question_number:03d}-{crop_index}.png"
        target = CROP_OUTPUT_DIR / filename
        pixmap.save(target)
        crops.append(
            {
                "src": f"{CROP_OUTPUT_PREFIX}/{filename}",
                "alt": f"{spec.title} {question_number}번 문제",
                "page": page_index + 1,
                "width": pixmap.width,
                "height": pixmap.height,
            }
        )
        crop_index += 1

    return crops


def crop_question_pages(spec: PdfSpec) -> dict[int, list[dict[str, object]]]:
    path = pdf_path(spec)
    by_question: dict[int, list[dict[str, object]]] = {}

    with fitz.open(path) as doc:
        starts, answers, explanations = collect_question_anchors(
            doc, spec.expected_count, spec.filename
        )

        for index, start in enumerate(starts):
            question_number = index + 1
            next_start = starts[index + 1] if index + 1 < len(starts) else None
            question_end_coord = next_start.coord if next_start else linear_coord(len(doc), 0)
            question_explanations = [
                explanation
                for explanation in explanations
                if start.coord < explanation.coord < question_end_coord
            ]
            answer_search_end = (
                question_explanations[0].coord if question_explanations else question_end_coord
            )
            question_answers = [
                answer for answer in answers if start.coord < answer.coord < answer_search_end
            ]
            crop_index = 1
            segment_page = start.page_index
            segment_y = start.y - CROP_MARGIN_TOP

            if not question_answers:
                end_page_index = next_start.page_index if next_start else len(doc) - 1
                end_y = next_start.y - CROP_MARGIN_BOTTOM if next_start else doc[-1].rect.height
                by_question[question_number] = crop_between(
                    doc,
                    spec,
                    question_number,
                    crop_index,
                    segment_page,
                    segment_y,
                    end_page_index,
                    end_y,
                )
                continue

            by_question[question_number] = []
            for answer in question_answers:
                crops = crop_between(
                    doc,
                    spec,
                    question_number,
                    crop_index,
                    segment_page,
                    segment_y,
                    answer.page_index,
                    answer.y - CROP_MARGIN_BOTTOM,
                )
                by_question[question_number].extend(crops)
                crop_index += len(crops)
                segment_page = answer.page_index
                segment_y = answer.y + ANSWER_SKIP_HEIGHT

    return by_question


def find_question_starts(text: str, expected_count: int, filename: str) -> list[re.Match[str]]:
    starts: list[re.Match[str]] = []
    cursor = 0
    for number in range(1, expected_count + 1):
        pattern = re.compile(rf"(?m)^\s*{number}\.\s+")
        match = pattern.search(text, cursor)
        if not match:
            raise ValueError(f"{filename}: {number}번 문제 시작점을 찾지 못했습니다.")
        starts.append(match)
        cursor = match.end()
    return starts


def split_answer(block: str, filename: str, number: int) -> tuple[str, str, str]:
    body, explanation = split_explanation(block)
    answer_labels = list(re.finditer(r"(?m)^\s*답\s*(?::\s*(?P<first>.*)|$)", body))
    if not answer_labels:
        fallback = split_mines_table_answer(body)
        if fallback:
            question, answer = fallback
            return clean_block(question), clean_block(answer), clean_block(explanation)
        raise ValueError(f"{filename}: {number}번 문제의 정답 표식을 찾지 못했습니다.")

    first_label = answer_labels[0]
    if len(answer_labels) == 1:
        question = body[: first_label.start()].strip()
        first_answer_line = first_label.group("first") or ""
        answer = (first_answer_line + body[first_label.end() :]).strip()
    else:
        # Some source questions interleave answer labels between sub-questions.
        # Keep the whole prompt visible, but redact answer-label lines.
        question = redact_inline_answers(body)
        answer = summarize_interleaved_answers(answer_labels)

    return clean_block(question), clean_block(answer), clean_block(explanation)


def split_mines_table_answer(body: str) -> tuple[str, str] | None:
    match = re.search(r"(?m)^배열\s*<field>\s+배열\s*<mines>\s*$", body)
    if not match:
        return None

    mines_rows: list[str] = []
    for line in body[match.end() :].splitlines():
        values = re.findall(r"\d+", line)
        if len(values) >= 8:
            mines_rows.append(" ".join(values[-4:]))

    if not mines_rows:
        return None

    question = body[: match.start()].strip()
    answer = "배열 <mines>\n" + "\n".join(mines_rows)
    return question, answer


def split_explanation(text: str) -> tuple[str, str]:
    match = re.search(r"(?m)^\s*(?:\[\s*해설\s*\]|해설)\s*$", text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), text[match.end() :].strip()


def redact_inline_answers(text: str) -> str:
    text = re.sub(r"(?m)^(\s*답\s*:).*$", r"\1 [정답 숨김]", text)
    text = re.sub(r"(?m)^(\s*답\s*)$", r"\1\n[정답 숨김]", text)
    return text


def summarize_interleaved_answers(answer_labels: list[re.Match[str]]) -> str:
    circled = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
    lines = []
    for index, label in enumerate(answer_labels):
        value = (label.group("first") or "").strip()
        prefix = circled[index] if index < len(circled) else f"{index + 1}."
        lines.append(f"{prefix} {value}".rstrip())
    return "\n".join(lines)


def clean_block(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(
    spec: PdfSpec, crops_by_question: dict[int, list[dict[str, object]]]
) -> tuple[list[dict[str, object]], str]:
    path = pdf_path(spec)
    text = extract_pdf_text(path)
    starts = find_question_starts(text, spec.expected_count, spec.filename)
    intro = text[: starts[0].start()].strip()

    questions: list[dict[str, object]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[start.start() : end].strip()
        question, answer, explanation = split_answer(block, spec.filename, index + 1)

        if not question:
            raise ValueError(f"{spec.filename}: {index + 1}번 문제 본문이 비어 있습니다.")
        if not answer:
            raise ValueError(f"{spec.filename}: {index + 1}번 정답이 비어 있습니다.")

        item: dict[str, object] = {
            "id": f"{spec.title}-{index + 1:03d}",
            "source": spec.title,
            "source_file": spec.filename,
            "number": index + 1,
            "question": question,
            "answer": answer,
            "explanation": explanation,
        }
        if crops_by_question.get(index + 1):
            item["question_images"] = crops_by_question[index + 1]
        questions.append(item)

    return questions, intro


def main() -> None:
    all_questions: list[dict[str, object]] = []
    sources: dict[str, dict[str, object]] = {}

    reset_crop_output_dir()
    for spec in PDFS:
        crops_by_question = crop_question_pages(spec)
        questions, intro = parse_pdf(spec, crops_by_question)
        if len(questions) != spec.expected_count:
            raise ValueError(
                f"{spec.filename}: {spec.expected_count}개를 기대했지만 {len(questions)}개가 추출됐습니다."
            )
        all_questions.extend(questions)
        sources[spec.title] = {
            "file": spec.filename,
            "expected_count": spec.expected_count,
            "actual_count": len(questions),
            "question_image_count": sum(len(images) for images in crops_by_question.values()),
            "intro": intro,
        }
        print(
            f"{spec.title}: {len(questions)}문제 추출, "
            f"문제 이미지 {sum(len(images) for images in crops_by_question.values())}개"
        )

    data = {
        "total_count": len(all_questions),
        "sources": sources,
        "questions": all_questions,
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 {len(all_questions)}문제를 {OUTPUT.name}에 저장했습니다.")


if __name__ == "__main__":
    main()
