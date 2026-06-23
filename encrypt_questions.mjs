import { readFile, writeFile } from "node:fs/promises";
import { webcrypto } from "node:crypto";

const INPUT_FILE = "questions.json";
const OUTPUT_FILE = "questions.enc.json";
const ITERATIONS = 250000;

function toBase64(bytes) {
  return Buffer.from(bytes).toString("base64");
}

function readHidden(prompt) {
  if (process.env.QUIZ_PASSWORD) {
    return Promise.resolve(process.env.QUIZ_PASSWORD);
  }

  return new Promise((resolve) => {
    const stdin = process.stdin;
    const stdout = process.stdout;
    let value = "";

    stdout.write(prompt);
    stdin.setRawMode?.(true);
    stdin.resume();
    stdin.setEncoding("utf8");

    function cleanup() {
      stdin.setRawMode?.(false);
      stdin.pause();
      stdin.off("data", onData);
      stdout.write("\n");
    }

    function onData(char) {
      if (char === "\u0003") {
        cleanup();
        process.exit(130);
      }
      if (char === "\r" || char === "\n" || char === "\u0004") {
        cleanup();
        resolve(value);
        return;
      }
      if (char === "\u007f") {
        value = value.slice(0, -1);
        return;
      }
      value += char;
      stdout.write("*");
    }

    stdin.on("data", onData);
  });
}

async function deriveKey(password, salt) {
  const baseKey = await webcrypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveKey"]
  );

  return webcrypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"]
  );
}

async function main() {
  const password = await readHidden("Quiz password: ");
  if (!password) {
    throw new Error("Password is required.");
  }

  const plainText = await readFile(INPUT_FILE, "utf8");
  JSON.parse(plainText);

  const salt = webcrypto.getRandomValues(new Uint8Array(16));
  const iv = webcrypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt);
  const encrypted = await webcrypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plainText)
  );

  const payload = {
    version: 1,
    cipher: "AES-GCM",
    kdf: "PBKDF2-SHA256",
    iterations: ITERATIONS,
    salt: toBase64(salt),
    iv: toBase64(iv),
    data: toBase64(new Uint8Array(encrypted))
  };

  await writeFile(OUTPUT_FILE, `${JSON.stringify(payload)}\n`, "utf8");
  console.log(`Wrote ${OUTPUT_FILE}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
