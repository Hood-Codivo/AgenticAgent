import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from price_action_data import load_and_preprocess_data
from trading_env import ForexTradingEnv


def run_one_episode(model, vec_env, deterministic=True):
    obs = vec_env.reset()
    equity_curve = []
    closed_trades = []

    while True:
        action, _ = model.predict(obs, deterministic=deterministic)
        step_out = vec_env.step(action)

        if len(step_out) == 4:
            obs, rewards, dones, infos = step_out
            done = bool(dones[0])
        else:
            obs, rewards, terminated, truncated, infos = step_out
            done = bool(terminated[0] or truncated[0])

        equity_curve.append(vec_env.get_attr("equity_usd")[0])

        trade_info = vec_env.get_attr("last_trade_info")[0]
        if isinstance(trade_info, dict) and trade_info.get("event") == "CLOSE":
            closed_trades.append(trade_info)

        if done: 
            break

    return equity_curve, closed_trades


def main():
    parser = argparse.ArgumentParser(description="Backtest a trained EURUSD PPO model.")
    parser.add_argument(
        "--data-path",
        default="data/EURUSD_Candlestick_1_Hour_BID_01.07.2020-15.07.2023.csv",
        help="CSV file used for evaluation. Defaults to the original training dataset.",
    )
    parser.add_argument(
        "--model-path",
        default="model_eurusd_best",
        help="Path to the Stable Baselines model, with or without .zip.",
    )
    args = parser.parse_args()

    # Choose the dataset you want to evaluate on - use same data as training
    file_path = args.data_path
    df, feature_cols = load_and_preprocess_data(file_path)

    # If you want a true OOS test here, split and use only the test slice:
    split_idx = int(len(df) * 0.8)
    test_df = df.iloc[split_idx:].copy()

    # MUST match training params exactly
    SL_OPTS = [5, 10, 15, 25, 30, 60, 90, 120]
    TP_OPTS = [5, 10, 15, 25, 30, 60, 90, 120]
    WIN = 30

    print("=" * 60)
    print("LOADING TRAINED MODEL...")
    print("=" * 60)

    test_env = ForexTradingEnv(
        df=test_df,
        window_size=WIN,
        sl_options=SL_OPTS,
        tp_options=TP_OPTS,
        spread_pips=1.0,
        commission_pips=0.0,
        max_slippage_pips=0.2,
        random_start=False,
        episode_max_steps=None,
        feature_columns=feature_cols,
        hold_reward_weight=0.00,
        open_penalty_pips=0.0,
        time_penalty_pips=0.0,
        unrealized_delta_weight=0.0
    )

    vec_test_env = DummyVecEnv([lambda: test_env])

    # Load best model
    try:
        model = PPO.load(args.model_path, env=vec_test_env)
        print(f"✓ Model loaded successfully: {args.model_path}")
    except Exception as e:
        print(f"✗ Error loading model: {e}")
        return

    print("=" * 60)
    print("RUNNING BACKTEST ON TEST DATA...")
    print("=" * 60)

    equity_curve, closed_trades = run_one_episode(model, vec_test_env, deterministic=True)

    # Statistics
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    if equity_curve:
        initial_equity = equity_curve[0]
        final_equity = equity_curve[-1]
        max_equity = max(equity_curve)
        min_equity = min(equity_curve)
        profit_loss = final_equity - initial_equity
        
        print(f"Initial Equity:  ${initial_equity:,.2f}")
        print(f"Final Equity:    ${final_equity:,.2f}")
        print(f"Profit/Loss:     ${profit_loss:,.2f}")
        print(f"Max Drawdown:    ${min_equity:,.2f}")
        print(f"Peak Equity:     ${max_equity:,.2f}")
        print(f"Total Steps:     {len(equity_curve)}")
    
    # Save trades
    if closed_trades:
        trades_df = pd.DataFrame(closed_trades)
        out_csv = "trade_history_output.csv"
        trades_df.to_csv(out_csv, index=False)
        print(f"\n✓ Closed trades saved: {out_csv}")
        print(f"  Number of trades: {len(trades_df)}")
    else:
        print("\nNo closed trades recorded.")

    # Plot and save equity curve
    print("\n" + "=" * 60)
    print("SAVING EQUITY CURVE PLOT...")
    print("=" * 60)
    
    try:
        plt.figure(figsize=(14, 7))
        plt.plot(equity_curve, label="Equity Curve", linewidth=2, color='blue')
        plt.axhline(y=equity_curve[0], color='green', linestyle='--', alpha=0.5, label='Initial Equity')
        plt.fill_between(range(len(equity_curve)), equity_curve, alpha=0.3)
        
        plt.title("Model Backtest: Equity Curve (Out-of-Sample Test Data)", fontsize=14, fontweight='bold')
        plt.xlabel("Steps", fontsize=12)
        plt.ylabel("Equity ($)", fontsize=12)
        plt.legend(fontsize=11)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        plot_file = "test_equity_curve.png"
        plt.savefig(plot_file, dpi=150)
        print(f"✓ Plot saved: {plot_file}")
        plt.close()
    except Exception as e:
        print(f"✗ Error saving plot: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
