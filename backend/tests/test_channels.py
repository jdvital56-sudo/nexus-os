"""Профили каналов: второй канал появился, первый не пошевелился.

Правило из CLAUDE.md про обе стороны здесь не формальность. Всё, что
разъезжается между каналами — стиль, хэндл, обложка, голос сценариста —
раньше было глобальным. Любая правка профилей может незаметно утащить
«Точку опоры» в оформление «Я знаю, почему», и заметит это не тест, а
фаундер в опубликованной карусели. Поэтому на каждое «у нового канала
теперь так» ниже стоит парное «у старого по-прежнему эдак».

Отдельно и жёстче остального проверяется анонимность: ведущая канала
«Я знаю, почему» не должна попасть на обложку даже тогда, когда портрет
лежит на месте и переменная окружения прямо на него указывает.
"""
import pytest
from PIL import Image

from backend.services import carousel as C
from backend.services import channels


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Каждый тест стартует без настроек канала — иначе они текут между тестами."""
    monkeypatch.delenv("NEXUS_CHANNEL", raising=False)
    monkeypatch.delenv("NEXUS_CHANNEL_HANDLE", raising=False)
    monkeypatch.delenv("NEXUS_CAROUSEL_COVER", raising=False)


# --- какой канал выбран ------------------------------------------------


def test_bez_nastroyki_kanal_prezhniy():
    """Без переменной — «Точка опоры». Поведение завода не изменилось."""
    ch = channels.current()
    assert ch.id == "tochka"
    assert ch.carousel_style == "beige"
    assert ch.show_presenter is True
    assert ch.voice == "", "у старого канала голоса не было — и не появилось"


def test_peremennaya_pereklyuchaet_kanal(monkeypatch):
    monkeypatch.setenv("NEXUS_CHANNEL", "znayu")
    ch = channels.current()
    assert ch.id == "znayu"
    assert ch.carousel_style == "znayu"
    assert ch.show_presenter is False
    assert ch.voice, "у нового канала голос сценариста обязан быть"


def test_neizvestnyy_kanal_ne_ronyaet_zavod(monkeypatch):
    """Опечатка в настройке не должна останавливать сборку контента."""
    monkeypatch.setenv("NEXUS_CHANNEL", "opechatka")
    assert channels.current().id == "tochka"


# --- анонимность ведущей ------------------------------------------------


def test_anonimnyy_kanal_ne_beret_portret_dazhe_iz_peremennoy(monkeypatch, tmp_path):
    """Главный тест файла: лицо ведущей не попадает на обложку никогда.

    Портрет существует и переменная указывает прямо на него — и всё равно
    обложка обязана остаться без него.
    """
    portrait = tmp_path / "portret.jpg"
    Image.new("RGB", (100, 100), (200, 150, 120)).save(portrait, "JPEG")

    monkeypatch.setenv("NEXUS_CHANNEL", "znayu")
    monkeypatch.setenv("NEXUS_CAROUSEL_COVER", str(portrait))

    assert C.cover_photo() is None


def test_kanal_s_vedushchey_portret_po_prezhnemu_beret(monkeypatch, tmp_path):
    """Обратная сторона: у «Точки опоры» портрет как работал, так и работает."""
    portrait = tmp_path / "vera.jpg"
    Image.new("RGB", (100, 100), (200, 150, 120)).save(portrait, "JPEG")

    monkeypatch.setenv("NEXUS_CAROUSEL_COVER", str(portrait))

    assert C.cover_photo() == portrait


# --- подпись в подвале --------------------------------------------------


def test_hendl_novogo_kanala_iz_profilya(monkeypatch):
    monkeypatch.setenv("NEXUS_CHANNEL", "znayu")
    assert channels.handle() == "@znayu.pochemu"


def test_peremennaya_hendla_silnee_profilya(monkeypatch):
    """На «Точке опоры» хэндл жил в переменной — профиль не смеет его затирать."""
    monkeypatch.setenv("NEXUS_CHANNEL", "znayu")
    monkeypatch.setenv("NEXUS_CHANNEL_HANDLE", "@tochka.opory.tv")
    assert channels.handle() == "@tochka.opory.tv"


def test_bez_peremennoy_i_bez_profilya_podval_pustoy():
    """У «Точки опоры» хэндла в профиле нет — подвал остаётся без подписи."""
    assert channels.handle() == ""


# --- стиль в пикселях ---------------------------------------------------


def test_stil_novogo_kanala_temnyy_i_tyoplyy(tmp_path):
    """Фаундер просил «не серое и не грустное» — проверяем цветом, а не на глаз.

    Тёплый значит красного в фоне больше, чем синего. Серый — это когда
    каналы равны; ровно этого он и не хотел.
    """
    style = C.STYLES["znayu"]
    slide = C.Slide(text="Ты не ленивая.", kind="body")
    image = C.render_slide(slide, style, "@znayu.pochemu")

    r, g, b = image.getpixel((5, 5))
    assert r + g + b < 200, "фон обязан быть тёмным"
    assert r > b, "фон обязан быть тёплым, а не холодно-серым"


def test_stil_tochki_opory_ne_izmenilsya():
    """Обратная сторона: беж «Точки опоры» остался ровно тем же."""
    assert C.STYLES["beige"].bg == (214, 180, 143)
    assert C.DEFAULT_STYLE == "beige"


# --- голос сценариста ---------------------------------------------------


@pytest.mark.parametrize(
    "trebovanie",
    ["механизм", "инструмент", "применение", "диагноз", "словами"],
)
def test_golos_soderzhit_obyazatelnye_pravila(trebovanie):
    """Голос без этих правил — это не голос канала, а общий копирайтинг.

    Проверяем по одному, чтобы упавший тест сразу называл потерянное правило.
    """
    assert trebovanie in channels.CHANNELS["znayu"].voice.lower()


def test_golos_zapreshchaet_upominat_ii_i_imya():
    """Анонимность держится не только на обложке, но и в тексте сценария."""
    voice = channels.CHANNELS["znayu"].voice.lower()
    assert "имя ведущей" in voice
    assert "ии" in voice
