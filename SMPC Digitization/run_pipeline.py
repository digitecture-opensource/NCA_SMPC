# run_pipeline.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Steps
from Step_10_Substance_map import run_step_10_substance_map
from Step_30_load_MHRA_orphan_register import run_step_30_load_mhra_orphan_register
from Step_20_Fetch_MP_MA import run_step_20_fetch_MP_MA
from Step_40_Admin_product import run_step_40_admin_product


def load_repo_env():
    """
    Loads repo-level .env once for the whole pipeline.
    Adjust the path as needed.
    """
    here = Path(__file__).resolve().parent
    candidate = here / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=True)
        return

    fallback = Path(r"C:\Users\anilp\OneDrive - digitecture.co.uk\Code\CV Managament_Github JS Code\CV_Management\.env")
    if fallback.exists():
        load_dotenv(fallback, override=True)


def _parse_steps(steps_env: str):
    """
    STEPS can be: "10", "30", "10,30", or "all"
    Default: "all"
    """
    s = (steps_env or "all").strip().lower()
    if not s or s == "all":
        return {"10", "20", "30", "40"}

    parts = {p.strip() for p in s.split(",") if p.strip()}
    # allow e.g. "step10" too
    cleaned = set()
    for p in parts:
        p = p.replace("step", "").strip()
        cleaned.add(p)
    return cleaned


def main():
    load_repo_env()

    # Which steps to run
    steps_to_run = _parse_steps(os.getenv("SMPC_STEPS"))

    print("=== Pipeline start ===")
    print(f"Steps requested: {sorted(steps_to_run)}")

    # ----------------------------
    # Step 10 - Substance mapping
    # ----------------------------
    if "10" in steps_to_run:
        input_jsonl = "smpc_payloads.jsonl"
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

        only_ids_env = os.getenv("ONLY_SMPC_IDS", "").strip()
        only_smpc_ids = None
        if only_ids_env:
            only_smpc_ids = {int(x.strip()) for x in only_ids_env.split(",") if x.strip()}

        dry_run = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
        sleep_sec = float(os.getenv("SLEEP_BETWEEN_CALLS_SEC", "0"))

        print("\n--- Running Step 10 (Substance mapping) ---")
        print(f"Input JSONL: {input_jsonl}")
        print(f"Model: {model}")
        print(f"Dry run: {dry_run}")
        print(f"Only IDs: {only_smpc_ids}")

        stats = run_step_10_substance_map(
            input_jsonl=input_jsonl,
            model=model,
            dry_run=dry_run,
            only_smpc_ids=only_smpc_ids,
            sleep_between_calls_sec=sleep_sec,
        )
        print(f"Step 10 stats: {stats}")
    
    if "20" in steps_to_run:
        print("\n--- Running Step 20 (Fetch MP MA) ---")
        stats = run_step_20_fetch_MP_MA()

    # ----------------------------
    # Step 30 - MHRA Orphan Register
    # ----------------------------
    if "40" in steps_to_run:
        print("\n--- Running Step 40 (Admin Product) ---")
        stats = run_step_40_admin_product()
        print(f"Step 40 stats: {stats}")

    if "30" in steps_to_run:
        print("\n--- Running Step 30 (MHRA Orphan Register load) ---")

        # Put your downloaded CSVs in a folder and set these in .env (recommended),
        # or hard-code the full paths here.
        current_csv = os.getenv("MHRA_ORPHAN_CURRENT_CSV", "").strip()
        expired_csv = os.getenv("MHRA_ORPHAN_EXPIRED_CSV", "").strip()

        # Simple fallback if you want a single folder env var:
        # e.g. MHRA_ORPHAN_DIR=C:\...\Data Downloads
        if (not current_csv or not expired_csv):
            base_dir = os.getenv("MHRA_ORPHAN_DIR", "").strip()
            if base_dir:
                base_dir = Path(base_dir)
                if not current_csv:
                    current_csv = str(base_dir / "Orphan_Register__3__current.csv")
                if not expired_csv:
                    expired_csv = str(base_dir / "Orphan_Register__3__expired.csv")

        if not current_csv or not expired_csv:
            raise ValueError(
                "Step 30 needs CSV paths. Set either:\n"
                "  MHRA_ORPHAN_CURRENT_CSV and MHRA_ORPHAN_EXPIRED_CSV\n"
                "or\n"
                "  MHRA_ORPHAN_DIR (folder containing Orphan_Register__3__current.csv and Orphan_Register__3__expired.csv)"
            )

       
        print(f"Current CSV: {current_csv}")
        print(f"Expired CSV: {expired_csv}")
     

        run_step_30_load_mhra_orphan_register(
            current_csv_path=current_csv,
            expired_csv_path=expired_csv,
            
        )

    print("\n=== Pipeline complete ===")


if __name__ == "__main__":
    main()
    
    