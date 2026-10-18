import subprocess
from pathlib import Path

import pytest

from diffsmith.config import Config


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny Python project with passing tests, committed to git."""
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "__init__.py").write_text("")
    (tmp_path / "shop" / "pricing.py").write_text(
        "def apply_discount(price, percent):\n"
        "    return round(price * (1 - percent / 100), 2)\n"
    )
    (tmp_path / "shop" / "cart.py").write_text(
        "from shop.pricing import apply_discount\n\n\n"
        "class Cart:\n"
        "    def __init__(self):\n"
        "        self.items = []\n\n"
        "    def add(self, name, price):\n"
        "        self.items.append((name, price))\n\n"
        "    def total(self, discount=0):\n"
        "        return apply_discount(sum(p for _, p in self.items), discount)\n"
    )
    (tmp_path / "README.md").write_text("# Shop\nA tiny shopping cart.\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cart.py").write_text(
        "from shop.cart import Cart\n\n\n"
        "def test_total():\n"
        "    c = Cart()\n"
        "    c.add('pen', 2.0)\n"
        "    c.add('book', 10.0)\n"
        "    assert c.total() == 12.0\n"
        "    assert c.total(discount=50) == 6.0\n"
    )
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.embedder = "hashing"
    cfg.test_command = None  # auto-detect
    return cfg
