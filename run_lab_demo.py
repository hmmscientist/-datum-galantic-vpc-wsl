#!/usr/bin/env python3
# =============================================================================
# Datum Galactic VPC Lab - Demo Runner Script
# =============================================================================
# Author: Sajjad Ahmed
# Company: Multi Naturals Inc.
# Created: January 2026
# License: MIT
# Datum Source: https://www.datum.net/docs/galactic-vpc/#galactic-agent
#
# PURPOSE:
# This script provides an interactive demo of the Datum Galactic VPC lab.
# It starts the topology, runs connectivity tests, demonstrates SRv6 routing,
# and shows MQTT route injection.
#
# PREREQUISITES:
# 1. WSL2 with Ubuntu 22.04 installed
# 2. Docker Engine installed in WSL (NOT Docker Desktop)
# 3. Containerlab and Netlab installed
# 4. Lab setup completed (run setup_wsl_lab.py first)
#
# USAGE:
# Run from Windows PowerShell or Command Prompt:
#   python run_lab_demo.py
#
# Or run specific demo steps:
#   python run_lab_demo.py --start       # Start lab only
#   python run_lab_demo.py --test        # Run connectivity tests
#   python run_lab_demo.py --mqtt        # Test MQTT route injection
#   python run_lab_demo.py --stop        # Stop lab
#   python run_lab_demo.py --status      # Check lab status
#
# DEMO FLOW:
# 1. Start the lab topology (3 FRR routers: SJC, IAD, AMS)
# 2. Wait for ISIS adjacencies to form
# 3. Verify SRv6 locators are advertised
# 4. Test connectivity between POPs
# 5. Start galactic-agent
# 6. Inject routes via MQTT
# 7. Verify routes in kernel
# 8. Interactive shell for exploration
#
# =============================================================================

import subprocess
import sys
import os
import time
import argparse
import threading
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# WSL distribution name
WSL_DISTRO = "Ubuntu-22.04"

# Lab directory in WSL
WSL_LAB_DIR = "~/datum/galantic-vpc"

# Topology nodes
NODES = {
    "sjc": {"name": "San Jose", "loopback": "10.255.0.1", "srv6": "fc00:0:1::"},
    "iad": {"name": "N. Virginia", "loopback": "10.255.0.2", "srv6": "fc00:0:2::"},
    "ams": {"name": "Amsterdam", "loopback": "10.255.0.3", "srv6": "fc00:0:3::"},
}

# Colors for terminal output
class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN} {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

def print_step(step_num, text):
    """Print a step indicator"""
    print(f"{Colors.GREEN}[Step {step_num}]{Colors.ENDC} {text}")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")

def run_wsl(command, distro=WSL_DISTRO, capture_output=True, timeout=60):
    """Run a command inside WSL"""
    full_command = f'wsl -d {distro} -- bash -c "{command}"'
    
    try:
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        print_warning(f"Command timed out: {command[:50]}...")
        return None

def run_wsl_interactive(command, distro=WSL_DISTRO):
    """Run an interactive command in WSL (shows output in real-time)"""
    full_command = f'wsl -d {distro} -- bash -c "{command}"'
    subprocess.run(full_command, shell=True)

def check_lab_running():
    """Check if the lab is currently running"""
    result = run_wsl("docker ps --filter 'name=clab-galactic' --format '{{.Names}}'")
    if result and result.stdout.strip():
        return True
    return False

def wait_with_spinner(seconds, message):
    """Wait with a spinner animation"""
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    end_time = time.time() + seconds
    i = 0
    while time.time() < end_time:
        remaining = int(end_time - time.time())
        print(f"\r{Colors.CYAN}{spinner[i % len(spinner)]} {message} ({remaining}s remaining){Colors.ENDC}", end='', flush=True)
        time.sleep(0.1)
        i += 1
    print(f"\r{' ' * 60}\r", end='')  # Clear line

# =============================================================================
# DEMO FUNCTIONS
# =============================================================================

def start_lab():
    """Start the lab topology"""
    print_header("Starting Galactic VPC Lab")
    
    # Check if already running
    if check_lab_running():
        print_warning("Lab is already running")
        return True
    
    # Check Docker is running
    print_step(1, "Checking Docker service...")
    result = run_wsl("sudo service docker status")
    if result and "is not running" in result.stdout:
        print_info("Starting Docker service...")
        run_wsl("sudo service docker start")
        time.sleep(2)
    print_success("Docker is running")
    
    # Start the lab
    print_step(2, "Starting lab topology with netlab...")
    print_info("This may take 1-2 minutes...")
    
    result = run_wsl(f"cd {WSL_LAB_DIR} && sudo netlab up", timeout=180)
    
    if result and result.returncode == 0:
        print_success("Lab topology started")
    else:
        print_error("Failed to start lab")
        if result:
            print(result.stderr)
        return False
    
    # Wait for ISIS to converge
    print_step(3, "Waiting for ISIS adjacencies to form...")
    wait_with_spinner(30, "Waiting for ISIS convergence")
    
    # Verify ISIS neighbors
    print_step(4, "Verifying ISIS neighbors...")
    result = run_wsl("docker exec clab-galactic_vpc-sjc vtysh -c 'show isis neighbor'")
    if result and result.stdout:
        print(f"\n{Colors.CYAN}ISIS Neighbors on SJC:{Colors.ENDC}")
        print(result.stdout)
        if "iad" in result.stdout.lower() or "ams" in result.stdout.lower():
            print_success("ISIS adjacencies established")
        else:
            print_warning("ISIS adjacencies may still be forming")
    
    return True

def stop_lab():
    """Stop the lab topology"""
    print_header("Stopping Galactic VPC Lab")
    
    if not check_lab_running():
        print_warning("Lab is not running")
        return True
    
    print_step(1, "Stopping lab topology...")
    result = run_wsl(f"cd {WSL_LAB_DIR} && sudo netlab down --cleanup", timeout=120)
    
    if result and result.returncode == 0:
        print_success("Lab stopped successfully")
    else:
        print_warning("Lab may not have stopped cleanly")
    
    return True

def check_status():
    """Check lab status"""
    print_header("Lab Status")
    
    # Check if lab is running
    print_step(1, "Checking container status...")
    result = run_wsl("docker ps --filter 'name=clab-galactic' --format 'table {{.Names}}\t{{.Status}}'")
    if result and result.stdout.strip():
        print(f"\n{Colors.CYAN}Running Containers:{Colors.ENDC}")
        print(result.stdout)
    else:
        print_warning("No lab containers running")
        return False
    
    # Check bridges
    print_step(2, "Checking Linux bridges...")
    result = run_wsl("brctl show | grep -E 'galactic|netlab'")
    if result and result.stdout:
        print(f"\n{Colors.CYAN}Lab Bridges:{Colors.ENDC}")
        print(result.stdout)
    
    # Check ISIS status on each node
    print_step(3, "Checking ISIS status...")
    for node, info in NODES.items():
        result = run_wsl(f"docker exec clab-galactic_vpc-{node} vtysh -c 'show isis neighbor' 2>/dev/null | head -5")
        if result and result.stdout:
            neighbor_count = result.stdout.count("Up")
            print(f"  {Colors.GREEN}✓{Colors.ENDC} {info['name']} ({node}): {neighbor_count} ISIS neighbors")
    
    # Check SRv6 locators
    print_step(4, "Checking SRv6 locators...")
    result = run_wsl("docker exec clab-galactic_vpc-sjc vtysh -c 'show segment-routing srv6 locator'")
    if result and result.stdout and "fc00" in result.stdout:
        print_success("SRv6 locators configured")
    else:
        print_warning("SRv6 locators may not be configured")
    
    return True

def run_connectivity_tests():
    """Run connectivity tests between POPs"""
    print_header("Running Connectivity Tests")
    
    if not check_lab_running():
        print_error("Lab is not running. Start it first with: python run_lab_demo.py --start")
        return False
    
    tests = [
        ("SJC → IAD (IPv4)", "sjc", f"ping -c 3 {NODES['iad']['loopback']}"),
        ("SJC → AMS (IPv4)", "sjc", f"ping -c 3 {NODES['ams']['loopback']}"),
        ("SJC → AMS (SRv6)", "sjc", f"ping -c 3 {NODES['ams']['srv6']}1"),
        ("IAD → SJC (IPv4)", "iad", f"ping -c 3 {NODES['sjc']['loopback']}"),
        ("AMS → SJC (SRv6)", "ams", f"ping -c 3 {NODES['sjc']['srv6']}1"),
    ]
    
    results = []
    for i, (name, node, cmd) in enumerate(tests, 1):
        print_step(i, f"Testing {name}...")
        result = run_wsl(f"docker exec clab-galactic_vpc-{node} {cmd}", timeout=30)
        
        if result and result.returncode == 0 and "0% packet loss" in result.stdout:
            print_success(f"{name}: PASSED")
            results.append(True)
        else:
            print_error(f"{name}: FAILED")
            results.append(False)
    
    # Summary
    print(f"\n{Colors.BOLD}Test Summary:{Colors.ENDC}")
    passed = sum(results)
    total = len(results)
    if passed == total:
        print_success(f"All {total} tests passed!")
    else:
        print_warning(f"{passed}/{total} tests passed")
    
    return all(results)

def test_mqtt_injection():
    """Test MQTT route injection"""
    print_header("Testing MQTT Route Injection")
    
    if not check_lab_running():
        print_error("Lab is not running. Start it first.")
        return False
    
    # Check if Mosquitto is running
    print_step(1, "Checking Mosquitto MQTT broker...")
    result = run_wsl("pgrep mosquitto")
    if not result or not result.stdout.strip():
        print_info("Starting Mosquitto...")
        run_wsl("sudo service mosquitto start")
        time.sleep(2)
    print_success("Mosquitto is running")
    
    # Check if galactic-agent is running
    print_step(2, "Checking galactic-agent...")
    result = run_wsl("pgrep -f galactic-agent")
    if not result or not result.stdout.strip():
        print_warning("galactic-agent is not running")
        print_info("Start it in another terminal with:")
        print(f"  {Colors.CYAN}cd {WSL_LAB_DIR}/galactic-agent{Colors.ENDC}")
        print(f"  {Colors.CYAN}sudo ./galactic-agent -config ../galactic-agent-config.yaml{Colors.ENDC}")
        print()
        
        response = input("Continue without agent? (y/n): ")
        if response.lower() != 'y':
            return False
    else:
        print_success("galactic-agent is running")
    
    # Run the test script
    print_step(3, "Injecting test routes via MQTT...")
    result = run_wsl(f"cd {WSL_LAB_DIR} && /usr/local/go/bin/go run test-mqtt-route.go", timeout=30)
    
    if result:
        print(result.stdout)
        if result.returncode == 0:
            print_success("MQTT route injection completed")
        else:
            print_warning("MQTT injection may have issues")
    
    # Check kernel routes
    print_step(4, "Checking kernel routing table...")
    result = run_wsl("ip -6 route show | grep -E '192.168.2|192.168.3|fc00'")
    if result and result.stdout:
        print(f"\n{Colors.CYAN}Kernel Routes:{Colors.ENDC}")
        print(result.stdout)
    else:
        print_info("No matching routes found (agent may not be running)")
    
    return True

def show_topology():
    """Display the lab topology"""
    print_header("Lab Topology")
    
    topology = """
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                    Galactic VPC Topology (SRv6)                             │
    │                                                                             │
    │    ┌─────────────────────────────────────────────────────────────────┐     │
    │    │           VPC Backbone Bridge: galactic_v_1                     │     │
    │    │           MTU: 9500 (Jumbo frames for SRv6)                     │     │
    │    └─────────────────────────────────────────────────────────────────┘     │
    │                                    │                                        │
    │         ┌──────────────────────────┼──────────────────────────┐            │
    │         │                          │                          │            │
    │         ▼                          ▼                          ▼            │
    │    ┌─────────┐              ┌─────────┐              ┌─────────┐          │
    │    │   SJC   │              │   IAD   │              │   AMS   │          │
    │    │San Jose │◄────────────►│N.Virginia│◄────────────►│Amsterdam│          │
    │    │ (FRR)   │   ISIS/BGP   │ (FRR)   │   ISIS/BGP   │ (FRR)   │          │
    │    └────┬────┘              └────┬────┘              └────┬────┘          │
    │         │                        │                        │                │
    │    Loopback:               Loopback:               Loopback:              │
    │    10.255.0.1              10.255.0.2              10.255.0.3              │
    │                                                                             │
    │    SRv6 Locators:                                                          │
    │    • SJC: fc00:0:1::/48                                                    │
    │    • IAD: fc00:0:2::/48                                                    │
    │    • AMS: fc00:0:3::/48                                                    │
    │                                                                             │
    │    Service Prefixes:                                                       │
    │    • SJC: 192.168.1.0/24                                                   │
    │    • AMS: 192.168.2.0/24                                                   │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘
    """
    print(f"{Colors.CYAN}{topology}{Colors.ENDC}")

def interactive_shell():
    """Open an interactive shell in WSL"""
    print_header("Interactive Shell")
    print_info("Opening WSL shell. Type 'exit' to return.")
    print_info(f"Lab directory: {WSL_LAB_DIR}")
    print()
    
    # Useful commands hint
    print(f"{Colors.BOLD}Useful Commands:{Colors.ENDC}")
    print(f"  {Colors.CYAN}docker exec -it clab-galactic_vpc-sjc vtysh{Colors.ENDC}  # FRR shell on SJC")
    print(f"  {Colors.CYAN}brctl show{Colors.ENDC}                                    # Show bridges")
    print(f"  {Colors.CYAN}ip -6 route show{Colors.ENDC}                              # Show IPv6 routes")
    print(f"  {Colors.CYAN}sudo netlab status{Colors.ENDC}                            # Lab status")
    print()
    
    os.system(f'wsl -d {WSL_DISTRO} --cd {WSL_LAB_DIR}')

def run_full_demo():
    """Run the complete demo sequence"""
    print_header("Datum Galactic VPC - Full Demo")
    
    print(f"""
    {Colors.CYAN}This demo will:{Colors.ENDC}
    1. Show the lab topology
    2. Start the lab (if not running)
    3. Verify ISIS adjacencies
    4. Run connectivity tests
    5. Test MQTT route injection
    6. Open interactive shell
    
    {Colors.WARNING}Press Ctrl+C at any time to stop the demo.{Colors.ENDC}
    """)
    
    input("Press Enter to start the demo...")
    
    try:
        # Show topology
        show_topology()
        input("\nPress Enter to continue...")
        
        # Start lab
        start_lab()
        input("\nPress Enter to continue...")
        
        # Check status
        check_status()
        input("\nPress Enter to continue...")
        
        # Run tests
        run_connectivity_tests()
        input("\nPress Enter to continue...")
        
        # MQTT test
        test_mqtt_injection()
        input("\nPress Enter to open interactive shell...")
        
        # Interactive shell
        interactive_shell()
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    
    print_header("Demo Complete")
    print(f"""
    {Colors.GREEN}Thank you for trying the Datum Galactic VPC Lab!{Colors.ENDC}
    
    {Colors.BOLD}Resources:{Colors.ENDC}
    • Tutorial:     {WSL_LAB_DIR}/TUTORIAL.md
    • Datum Docs:   https://www.datum.net/docs/galactic-vpc/
    • Author:       Sajjad Ahmed (https://www.linkedin.com/in/er-sajjad-ahmed/)
    
    {Colors.BOLD}To stop the lab:{Colors.ENDC}
    python run_lab_demo.py --stop
    """)

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Datum Galactic VPC Lab - Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_lab_demo.py           # Run full interactive demo
  python run_lab_demo.py --start   # Start lab only
  python run_lab_demo.py --test    # Run connectivity tests
  python run_lab_demo.py --mqtt    # Test MQTT route injection
  python run_lab_demo.py --stop    # Stop lab
  python run_lab_demo.py --status  # Check lab status
  python run_lab_demo.py --shell   # Open interactive shell
        """
    )
    parser.add_argument('--start', action='store_true', help='Start the lab topology')
    parser.add_argument('--stop', action='store_true', help='Stop the lab topology')
    parser.add_argument('--status', action='store_true', help='Check lab status')
    parser.add_argument('--test', action='store_true', help='Run connectivity tests')
    parser.add_argument('--mqtt', action='store_true', help='Test MQTT route injection')
    parser.add_argument('--topology', action='store_true', help='Show lab topology')
    parser.add_argument('--shell', action='store_true', help='Open interactive WSL shell')
    args = parser.parse_args()
    
    # Print banner
    print(f"""
{Colors.HEADER}╔══════════════════════════════════════════════════════════════════════╗
║           Datum Galactic VPC Lab - Demo Runner                       ║
║           Author: Sajjad Ahmed, Multi Naturals Inc.                  ║
╚══════════════════════════════════════════════════════════════════════╝{Colors.ENDC}
    """)
    
    # Handle specific commands
    if args.start:
        start_lab()
    elif args.stop:
        stop_lab()
    elif args.status:
        check_status()
    elif args.test:
        run_connectivity_tests()
    elif args.mqtt:
        test_mqtt_injection()
    elif args.topology:
        show_topology()
    elif args.shell:
        interactive_shell()
    else:
        # Run full demo if no specific command
        run_full_demo()

if __name__ == "__main__":
    main()
