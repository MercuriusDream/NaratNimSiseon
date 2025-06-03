
import subprocess
import sys
import os
import time
import signal
import psutil
from pathlib import Path
import shutil
import platform
import threading


def check_dependencies():
    """Check if all required dependencies are installed"""
    print("🔍 Checking dependencies...")
    missing_deps = []

    # Check Python version
    print(f"📋 Python version: {sys.version}")
    if sys.version_info < (3, 8):
        missing_deps.append("Python 3.8 or higher")

    # Check PostgreSQL
    print("📋 Checking PostgreSQL...")
    pg_path = shutil.which("psql")
    if not pg_path:
        missing_deps.append("PostgreSQL")
    else:
        print(f"✅ PostgreSQL found at: {pg_path}")

    # Check Redis
    print("📋 Checking Redis...")
    redis_path = shutil.which("redis-server")
    if not redis_path:
        missing_deps.append("Redis")
    else:
        print(f"✅ Redis found at: {redis_path}")

    # Check Python packages
    print("📋 Checking Python packages...")
    package_mappings = {
        "django": "django",
        "djangorestframework": "rest_framework",
        "celery": "celery",
        "redis": "redis",
        "psycopg2-binary": "psycopg2",
        "psutil": "psutil"
    }

    for package_name, import_name in package_mappings.items():
        try:
            __import__(import_name)
            print(f"✅ {package_name} is installed")
        except ImportError:
            print(f"❌ {package_name} is missing")
            missing_deps.append(f"Python package: {package_name}")

    if missing_deps:
        print("❌ Missing dependencies:")
        for dep in missing_deps:
            print(f"- {dep}")
        print("\nPlease install all dependencies before running the script.")
        sys.exit(1)

    print("✅ All dependencies check passed!")


def check_env_file():
    """Check if .env file exists and has required variables"""
    print("🔍 Checking environment file...")
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        print("❌ .env file not found!")
        print("Please create a .env file in the project root directory.")
        sys.exit(1)

    print(f"✅ .env file found at: {env_path}")

    required_vars = [
        'DJANGO_SECRET_KEY', 'PGDATABASE', 'PGUSER', 'PGPASSWORD',
        'ASSEMBLY_API_KEY', 'GEMINI_API_KEY'
    ]

    missing_vars = []
    with open(env_path) as f:
        env_content = f.read()
        for var in required_vars:
            if f"{var}=" in env_content:
                print(f"✅ {var} is set")
            else:
                print(f"❌ {var} is missing")
                missing_vars.append(var)

    if missing_vars:
        print("❌ Missing required environment variables in .env file:")
        for var in missing_vars:
            print(f"- {var}")
        sys.exit(1)

    print("✅ All environment variables check passed!")


def kill_process_by_port(port):
    """Kill process running on specified port"""
    print(f"🔍 Checking for processes on port {port}...")
    killed_any = False
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in proc.connections():
                if conn.laddr.port == port:
                    print(
                        f"💀 Killing process {proc.info['name']} (PID: {proc.info['pid']}) on port {port}"
                    )
                    proc.kill()
                    killed_any = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not killed_any:
        print(f"✅ No processes found on port {port}")


def log_output(pipe, prefix):
    """Log output from subprocess in real time"""
    for line in iter(pipe.readline, ''):
        if line:
            print(f"[{prefix}] {line.rstrip()}")


def start_service(command, name, working_dir=None):
    """Start a service and return the process"""
    print(f"🚀 Starting {name}...")
    print(f"📝 Command: {command}")
    if working_dir:
        print(f"📁 Working directory: {working_dir}")

    try:
        process = subprocess.Popen(command,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True,
                                   cwd=working_dir,
                                   bufsize=1)

        # Start a thread to log output in real time
        log_thread = threading.Thread(target=log_output,
                                      args=(process.stdout, name),
                                      daemon=True)
        log_thread.start()

        print(f"✅ {name} started with PID: {process.pid}")
        return process
    except Exception as e:
        print(f"❌ Error starting {name}: {str(e)}")
        sys.exit(1)


def is_redis_running():
    """Check if Redis is already running"""
    print("🔍 Checking if Redis is running...")
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✅ Redis is already running")
        return True
    except Exception as e:
        print(f"❌ Redis is not running: {e}")
        return False


def main():
    print("🎯 Starting Assembly Sentiment Analysis Services")
    print("=" * 50)

    print("\n📋 STEP 1: Dependency Check")
    check_dependencies()

    print("\n📋 STEP 2: Environment Check")
    check_env_file()

    print("\n📋 STEP 3: Killing existing processes")
    # Kill any existing processes on our ports
    kill_process_by_port(3000)  # Django (Replit port)
    kill_process_by_port(8000)  # Django
    kill_process_by_port(6379)  # Redis
    kill_process_by_port(5432)  # PostgreSQL

    # Get the project root directory
    project_root = Path(__file__).parent.absolute()
    print(f"📁 Project root: {project_root}")

    # Use system Python (no virtual environment in Replit)
    python_cmd = "python"
    print(f"🐍 Python executable: {python_cmd}")

    print("\n📋 STEP 4: Starting Services")

    # Start Redis (if not already running)
    redis_process = None
    if not is_redis_running():
        print("🚀 Starting Redis server...")
        # Use proper Redis configuration for Replit/Nix environment
        redis_cmd = "env LD_PRELOAD= redis-server --bind 0.0.0.0 --save \"\" --appendonly no --daemonize yes"
        redis_process = start_service(redis_cmd, "Redis")
        time.sleep(5)  # Wait longer for Redis to start

        # Verify Redis started
        if is_redis_running():
            print("✅ Redis started successfully")
        else:
            print("❌ Redis failed to start")
            sys.exit(1)

    # Run Django migrations and start server
    print("🚀 Starting Django migrations...")
    django_migrate_cmd = f"cd {project_root}/backend && {python_cmd} manage.py migrate"
    migrate_process = subprocess.run(django_migrate_cmd,
                                     shell=True,
                                     capture_output=True,
                                     text=True)

    if migrate_process.returncode == 0:
        print("✅ Django migrations completed successfully")
        if migrate_process.stdout:
            print(f"[MIGRATE-OUT] {migrate_process.stdout}")
    else:
        print("❌ Django migrations failed")
        if migrate_process.stderr:
            print(f"[MIGRATE-ERR] {migrate_process.stderr}")
        sys.exit(1)

    # Collect static files
    print("🚀 Collecting static files...")
    collectstatic_cmd = f"cd {project_root}/backend && {python_cmd} manage.py collectstatic --noinput"
    collectstatic_process = subprocess.run(collectstatic_cmd,
                                          shell=True,
                                          capture_output=True,
                                          text=True)

    if collectstatic_process.returncode == 0:
        print("✅ Static files collected successfully")
    else:
        print("⚠️ Static files collection failed, continuing anyway...")

    print("🚀 Starting Django server...")
    django_cmd = f"cd {project_root}/backend && {python_cmd} manage.py runserver 0.0.0.0:3000"
    django_process = start_service(django_cmd,
                                   "Django",
                                   working_dir=str(project_root / "backend"))
    time.sleep(5)  # Wait for Django to start

    # Start Celery worker
    print("🚀 Starting Celery worker...")
    celery_worker_cmd = f"cd {project_root}/backend && celery -A backend worker -l debug"
    celery_worker_process = start_service(celery_worker_cmd,
                                          "Celery-Worker",
                                          working_dir=str(project_root /
                                                          "backend"))
    time.sleep(3)  # Wait for Celery worker to start

    # Start Celery beat
    print("🚀 Starting Celery beat scheduler...")
    celery_beat_cmd = f"cd {project_root}/backend && celery -A backend beat -l debug"
    celery_beat_process = start_service(celery_beat_cmd,
                                        "Celery-Beat",
                                        working_dir=str(project_root /
                                                        "backend"))
    time.sleep(3)  # Wait for Celery beat to start

    print("\n🎉 All services started successfully!")
    print("=" * 50)
    print("🌐 Django server running at: http://localhost:3000")
    print("🌐 Django admin: http://localhost:3000/admin/")
    print("🌐 Django API: http://localhost:3000/api/")
    print("=" * 50)
    print("📊 Process monitoring:")
    print(f"  - Django PID: {django_process.pid}")
    print(f"  - Celery Worker PID: {celery_worker_process.pid}")
    print(f"  - Celery Beat PID: {celery_beat_process.pid}")
    if redis_process:
        print(f"  - Redis PID: {redis_process.pid}")
    print("=" * 50)
    print("✋ Press Ctrl+C to stop all services...")

    try:
        # Keep the script running and monitor processes
        while True:
            time.sleep(5)

            # Check if any process died
            processes = [("Django", django_process),
                         ("Celery-Worker", celery_worker_process),
                         ("Celery-Beat", celery_beat_process)]

            if redis_process:
                processes.append(("Redis", redis_process))

            for name, proc in processes:
                if proc.poll() is not None:
                    print(
                        f"⚠️ {name} process died with return code: {proc.returncode}"
                    )

    except KeyboardInterrupt:
        print("\n🛑 Stopping all services...")

        # Stop all processes gracefully
        processes_to_stop = [("Django", django_process),
                             ("Celery-Worker", celery_worker_process),
                             ("Celery-Beat", celery_beat_process)]

        if redis_process:
            processes_to_stop.append(("Redis", redis_process))

        for name, proc in processes_to_stop:
            if proc and proc.poll() is None:
                print(f"🛑 Stopping {name} (PID: {proc.pid})...")
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                    print(f"✅ {name} stopped gracefully")
                except subprocess.TimeoutExpired:
                    print(f"⚠️ {name} didn't stop gracefully, killing...")
                    proc.kill()
                    print(f"💀 {name} killed")
                except Exception as e:
                    print(f"❌ Error stopping {name}: {e}")

        print("✅ All services stopped.")


if __name__ == "__main__":
    main()
