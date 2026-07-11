from . import amazon, bestbuy, gamestop, pokemoncenter, target, walmart

CHECKERS = {
    "target": target.check,
    "walmart": walmart.check,
    "bestbuy": bestbuy.check,
    "gamestop": gamestop.check,
    "pokemoncenter": pokemoncenter.check,
    "amazon": amazon.check,
}
