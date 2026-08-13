"""Локальный сервер OmniVoice — держит модель в памяти, отвечает по HTTP.

Живёт в отдельном venv (voice_engine/.venv), потому что зависимости
OmniVoice (torch, transformers, gradio) конфликтуют с версиями
FastAPI/Starlette основного бэкенда — смешивать их в одном venv один раз
уже сломало тест (см. коммит с откатом). Процесс отдельный и по той же
причине: загрузка модели занимает время, поднимать её на каждый запрос
недопустимо для голосового ответа.

Веса модели (k2-fsa/OmniVoice) — CC-BY-NC, только некоммерческое
использование. Годится для личного Nexus OS, не годится для голоса в
клиентских продуктах (WhatsApp-боты клиник, spa/wellness-оффер).
"""
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("omnivoice-server")

HOST = "127.0.0.1"
PORT = 8421

_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model
    logger.info("Загружаю OmniVoice (это раз, дальше остаётся в памяти)…")
    from omnivoice import OmniVoice
    import torch

    # CPU для этой модели неприемлемо медленно (проверено: ~92с на короткую
    # фразу) — GPU обязателен, не оптимизация. Падаем на CPU только если
    # видеокарты в системе действительно нет.
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logger.info("Устройство: %s", device)
    _model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device)
    logger.info("OmniVoice загружен, sampling_rate=%s", _model.sampling_rate)
    return _model


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/health":
            ready = _model is not None
            body = json.dumps({"ready": ready}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/synthesize":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = str(payload.get("text") or "").strip()
            language = payload.get("language") or "ru"
            if not text:
                raise ValueError("text пустой")

            import soundfile as sf

            model = _load_model()
            audio = model.generate(text=text, language=language)[0]

            buf = BytesIO()
            sf.write(buf, audio, model.sampling_rate, format="WAV")
            wav_bytes = buf.getvalue()

            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_bytes)))
            self.end_headers()
            self.wfile.write(wav_bytes)
        except Exception as e:
            logger.exception("Синтез не удался")
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    # Модель грузим сразу при старте, не на первый запрос — иначе первый
    # реальный вопрос фаундера ждал бы загрузку минуту вместо ответа.
    _load_model()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("OmniVoice слушает http://%s:%d", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
