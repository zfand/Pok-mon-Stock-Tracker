from dataclasses import dataclass, field


@dataclass
class Hit:
    """A product listing found at a retailer."""

    retailer: str
    title: str
    url: str
    in_stock: bool          # purchasable right now (buy/preorder button live)
    price: str = ""         # display string, e.g. "$59.99"
    status: str = ""        # raw availability text, e.g. "PRE_ORDER", "SOLD_OUT"
    product_id: str = ""    # id of the matched product from config.yml

    @property
    def key(self) -> str:
        return f"{self.retailer}::{self.url}"


@dataclass
class CheckResult:
    """Outcome of one retailer's check run."""

    retailer: str
    hits: list[Hit] = field(default_factory=list)
    blocked: bool = False   # bot-blocked / captcha / 403
    error: str = ""
