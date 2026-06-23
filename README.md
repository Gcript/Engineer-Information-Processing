# Engineer-Information-Processing

정보처리기사 실기 학습을 위한 웹 퀴즈입니다.

## 주요 기능

- 오늘 학습용 랜덤 문제 출제
- 키워드찾기, SQL, 코드-제어문 분야별 학습
- 틀림/애매함으로 표시한 문제만 다시 푸는 오답 압축
- 키워드 검색을 통한 약점 주제 반복
- 브라우저 로컬 저장소를 이용한 풀이 기록 저장

## 파일 구성

- `index.html`: 기본 진입 파일
- `study_quiz.html`: 퀴즈 화면과 학습 로직
- `questions.enc.json`: 암호화된 문제 데이터
- `encrypt_questions.mjs`: 문제 데이터를 다시 암호화하는 스크립트

## 문제 데이터 보호

문제 데이터는 `questions.enc.json`으로 암호화되어 있습니다. 화면에서 비밀번호를 입력해야 브라우저 안에서 문제와 정답이 복호화됩니다.

평문 원본인 `questions.json`은 로컬에서만 관리하며 저장소에는 올리지 않습니다.

## 비밀번호 변경

로컬에 `questions.json`이 있는 상태에서 아래 명령을 실행합니다.

```bash
node encrypt_questions.mjs
```

새 비밀번호를 입력하면 `questions.enc.json`이 다시 생성됩니다. 변경 내용을 배포하려면 암호화된 파일을 커밋하고 푸시합니다.

```bash
git add questions.enc.json
git commit -m "Update quiz data password"
git push origin main
```
