import subprocess
import sys
import os
import time
import signal
import psutil
from pathlib import Path
import shutil
import platform

def check_dependencies():
    """Check if all required dependencies are installed"""
    missing_deps = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        missing_deps.append("Python 3.8 or higher")
    
    # Check PostgreSQL
    if platform.system() == "Windows":
        pg_path = shutil.which("psql")
        if not pg_path:
            missing_deps.append("PostgreSQL (https://www.postgresql.org/download/windows/)")
    else:
        pg_path = shutil.which("psql")
        if not pg_path:
            missing_deps.append("PostgreSQL (sudo apt-get install postgresql)")
    
    # Check Redis
    redis_path = shutil.which("redis-server")
    if not redis_path:
        if platform.system() == "Windows":
            missing_deps.append("Redis for Windows (https://github.com/microsoftarchive/redis/releases)")
        else:
            missing_deps.append("Redis (sudo apt-get install redis-server)")
    
    # Check Python packages
    package_mappings = {
        "django": "django",
        "djangorestframework": "rest_framework", 
        "celery": "celery",
        "redis": "redis",
        "streamlit": "streamlit",
        "psycopg2-binary": "psycopg2",
        "psutil": "psutil"
    }
    
    for package_name, import_name in package_mappings.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_deps.append(f"Python package: {package_name}")
    
    if missing_deps:
        print("Missing dependencies:")
        for dep in missing_deps:
            print(f"- {dep}")
        print("\nPlease install all dependencies before running the script.")
        sys.exit(1)

def kill_process_by_port(port):
    """Kill process running on specified port"""
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in proc.connections():
                if conn.laddr.port == port:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def start_service(command, name):
    """Start a service and return the process"""
    print(f"Starting {name}...")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return process
    except Exception as e:
        print(f"Error starting {name}: {str(e)}")
        sys.exit(1)

def main():
    print("Checking dependencies...")
    check_dependencies()
    
    print("\nKilling existing processes...")
    # Kill any existing processes on our ports
    kill_process_by_port(3000)  # Django
    kill_process_by_port(8501)  # Streamlit
    kill_process_by_port(6379)  # Redis
    kill_process_by_port(5432)  # PostgreSQL

    # Get the project root directory
    project_root = Path(__file__).parent.absolute()
    
    # Start PostgreSQL
    pg_process = start_service("pg_ctl -D /tmp/postgresql start", "PostgreSQL")
    time.sleep(3)  # Wait for PostgreSQL to start
    
    # Start Redis (if not already running)
    redis_process = start_service("redis-server", "Redis")
    time.sleep(2)  # Wait for Redis to start
    
    # Run Django migrations and start server
    django_cmd = f"cd {project_root}/backend && python manage.py migrate && python manage.py runserver 0.0.0.0:3000"
    django_process = start_service(django_cmd, "Django Server")
    time.sleep(3)  # Wait for Django to start
    
    # Start Celery worker
    celery_worker_cmd = f"cd {project_root}/backend && celery -A backend worker -l info"
    celery_worker_process = start_service(celery_worker_cmd, "Celery Worker")
    time.sleep(2)  # Wait for Celery worker to start
    
    # Start Celery beat
    celery_beat_cmd = f"cd {project_root}/backend && celery -A backend beat -l info"
    celery_beat_process = start_service(celery_beat_cmd, "Celery Beat")
    time.sleep(2)  # Wait for Celery beat to start
    
    # Start Streamlit frontend
    frontend_cmd = f"cd {project_root}/frontend && streamlit run app.py"
    frontend_process = start_service(frontend_cmd, "Streamlit Frontend")
    
    print("\nAll services started successfully!")
    print("Django server running at: http://localhost:3000")
    print("Streamlit frontend running at: http://localhost:8501")
    print("\nPress Ctrl+C to stop all services...")
    
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all services...")
        
        # Stop all processes
        for proc in [pg_process, django_process, celery_worker_process, 
                    celery_beat_process, frontend_process, redis_process]:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        
        print("All services stopped.")

if __name__ == "__main__":
    main() 