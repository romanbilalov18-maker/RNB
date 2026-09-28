import argparse

from bot.app import TradingBot
from bot.config import Config
from bot.runner import TradingRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot-1.0 trading bot")
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--reset-paper-portfolio", action="store_true", help="reset the local paper account to its original deposit and erase its history")
    parser.add_argument("--yes", action="store_true", help="confirm the destructive paper portfolio reset")
    args = parser.parse_args()

    config = Config.from_env()
    if args.reset_paper_portfolio:
        if config.execution_mode != "paper":
            parser.error("--reset-paper-portfolio is only available in paper mode")
        if not args.yes:
            parser.error("reset requires explicit confirmation: --reset-paper-portfolio --yes")
        bot = TradingBot(config)
        bot.paper_portfolio.reset(confirm=True)
        print(f"Paper portfolio reset to {bot.paper_portfolio.snapshot().cash:.2f} RUB; all virtual positions and trade history were cleared.")
        return
    if args.yes:
        parser.error("--yes can only be used with --reset-paper-portfolio")

    bot = TradingBot(config)
    print("Bot status:", bot.status())
    runner = TradingRunner(bot, interval_seconds=args.interval)
    for result in runner.run(args.cycles):
        print(f"cycle={result.cycle} status={result.status} signal={result.signal} reason={result.reason}")
        if config.execution_mode == "paper":
            account = bot.paper_portfolio.snapshot()
            print(f"  paper: cash={account.cash:.2f} RUB equity={account.equity:.2f} RUB realized_pnl={account.realized_pnl:.2f} RUB commission={account.total_commission:.2f} RUB positions={len(account.positions)}")
        diagnostics = getattr(result, "decision_diagnostics", None)
        if diagnostics:
            print("  decision: " + f"price={diagnostics['price']:.4f} regime={diagnostics['regime']} volatility={diagnostics['regime_volatility']:.6f} trend={diagnostics['regime_trend_strength']:.6f} regime_conf={diagnostics['regime_confidence']:.3f}")
            for name, item in diagnostics["strategies"].items():
                print(f"  strategy={name} signal={item['signal']} confidence={item['confidence']:.3f} reason={item['reason']}")
            meta = diagnostics["meta"]
            print("  meta: " + f"signal={meta['signal']} confidence={meta['confidence']:.3f} reason={meta['reason']} contributors={','.join(meta['contributors'])}")
            if diagnostics["model"] is not None:
                model = diagnostics["model"]
                print(f"  model: signal={model['signal']} confidence={model['confidence']:.3f} reason={model['reason']}")
            position = diagnostics.get("position")
            if position is not None:
                print("  position: " + f"action={position['action']} quantity={position['quantity']} target={position['target_quantity']} remaining={position['remaining_quantity']} strength={position['strength']:.3f} pnl_est={position['estimated_realized_pnl']:.2f} freed_cash={position['freed_cash']:.2f}")
            if diagnostics["outcome"] is not None:
                outcome = diagnostics["outcome"]
                print(f"  outcome: signal={outcome['signal']} confidence={outcome['confidence']:.3f} reason={outcome['reason']}")


if __name__ == "__main__":
    main()
