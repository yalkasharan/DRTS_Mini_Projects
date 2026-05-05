#!/usr/bin/env python3
"""
Run all simulator and analytical workflows for all test cases.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MINI_PROJECT_DIR = PROJECT_ROOT / "Required Files"

TEST_CASES = ["test_case_1", "test_case_2", "test_case_3"]


def run_command(cmd, description):
    """Run a command and report status."""
    print(f"\n{'='*72}")
    print(f" {description}")
    print(f"{'='*72}")
    try:
        result = subprocess.run(cmd, shell=True, check=True)
        print(f"[OK] {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] {description} failed with exit code {e.returncode}")
        return False


def main():
    print("\n" + "="*72)
    print(" DRTS TSN AVB CBS - Complete Workflow")
    print("="*72)
    
    success_count = 0
    total_count = 0
    
    # Run simulator for each test case
    print("\n" + "="*72)
    print(" PHASE 1: Simulation")
    print("="*72)
    for test_case in TEST_CASES:
        total_count += 1
        topology = MINI_PROJECT_DIR / test_case / "topology.json"
        streams = MINI_PROJECT_DIR / test_case / "streams.json"
        routes = MINI_PROJECT_DIR / test_case / "routes.json"
        
        cmd = (
            f"python simulator/main.py "
            f'"{topology}" "{streams}" "{routes}" '
            f"--warmup 10"
        )
        
        if run_command(cmd, f"Simulation - {test_case}"):
            success_count += 1
    
    # Run analytical for each test case
    print("\n" + "="*72)
    print(" PHASE 2: Analytical WCRT Analysis")
    print("="*72)
    for test_case in TEST_CASES:
        total_count += 1
        topology = MINI_PROJECT_DIR / test_case / "topology.json"
        streams = MINI_PROJECT_DIR / test_case / "streams.json"
        routes = MINI_PROJECT_DIR / test_case / "routes.json"
        
        cmd = (
            f"python analytical/main.py "
            f'"{topology}" "{streams}" "{routes}" '
            f"--idle-slope-a 0.5 --idle-slope-b 0.5"
        )
        
        if run_command(cmd, f"Analytical - {test_case}"):
            success_count += 1
    
    # Compare results
    print("\n" + "="*72)
    print(" PHASE 3: Comparison & Results")
    print("="*72)
    
    # Run comparison for the last test case (test-case-1 for reference)
    total_count += 1
    topology = MINI_PROJECT_DIR / "test_case_1" / "topology.json"
    streams = MINI_PROJECT_DIR / "test_case_1" / "streams.json"
    routes = MINI_PROJECT_DIR / "test_case_1" / "routes.json"
    
    cmd = (
        f"python compare_results.py "
        f'"{topology}" "{streams}" "{routes}"'
    )
    
    if run_command(cmd, "Compare simulation vs analytical"):
        success_count += 1
    
    # Generate plots
    print("\n" + "="*72)
    print(" PHASE 4: Plot Generation")
    print("="*72)
    total_count += 1
    if run_command("python results/generate_plots.py", "Generate visualization charts"):
        success_count += 1
    
    # Summary
    print("\n" + "="*72)
    print(" WORKFLOW SUMMARY")
    print("="*72)
    print(f"Completed: {success_count}/{total_count} steps")
    print(f"Results saved to: results/")
    print(f"Plots saved to: results/plots/")
    print("="*72 + "\n")
    
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
