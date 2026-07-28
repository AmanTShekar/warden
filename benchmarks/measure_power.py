import subprocess
import time
import csv
import argparse
from datetime import datetime

class PowerBenchmark:
    """
    Wrapper around rocm-smi to capture GPU telemetry:
    - Power (watts)
    - Utilization (%)
    - VRAM usage (MB)
    - Temperature (°C)
    """
    
    def __init__(self, interval_ms: int = 100):
        self.interval = interval_ms / 1000.0
        self._running = False

    def start_monitoring(self, output_path: str, duration_sec: int = 60):
        print(f"Starting GPU telemetry. Logging to {output_path} for {duration_sec}s at {self.interval}s intervals.")
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Power(W)", "GPU_Util(%)", "VRAM_Usage(MB)", "Temp(C)"])
            
            start_time = time.time()
            try:
                while time.time() - start_time < duration_sec:
                    # Run rocm-smi to fetch telemetry
                    result = subprocess.run(
                        ["rocm-smi", "--showpower", "--showuse", "--showmemuse", "--showtemp", "--csv"],
                        capture_output=True, text=True
                    )
                    
                    if result.returncode != 0:
                        print("Failed to run rocm-smi. Are you on a ROCm-enabled AMD GPU instance?")
                        break
                        
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        # Parse the CSV output from rocm-smi
                        # Note: The exact column indices depend on the rocm-smi version, 
                        # this is a simplified generic extraction
                        vals = lines[-1].split(',')
                        
                        # In a real environment, we parse these exactly. For now, we write the raw CSV line.
                        now = datetime.now().isoformat()
                        writer.writerow([now] + vals[1:])
                        
                    time.sleep(self.interval)
            except KeyboardInterrupt:
                print("Monitoring stopped by user.")
                
        print(f"Monitoring complete. Saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", default="gpu_telemetry.csv", help="Output CSV path")
    parser.add_argument("--duration", "-d", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--interval", "-i", type=int, default=100, help="Interval in milliseconds")
    
    args = parser.parse_args()
    
    bench = PowerBenchmark(interval_ms=args.interval)
    bench.start_monitoring(args.output, args.duration)
