import subprocess
import sys


def run_step(script_name):
    print(f"\n===== Running {script_name} =====")
    result = subprocess.run([sys.executable, script_name], check=False)

    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed with exit code {result.returncode}")

    print(f"✅ {script_name} completed successfully.")


if __name__ == "__main__":
    run_step("prepare_sequences.py")
    run_step("train_arimax.py")
    run_step("train_lstm.py")

    print("\n✅ Full retraining pipeline completed successfully.")