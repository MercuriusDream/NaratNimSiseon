
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


def kill_redis_processes():
    """Kill all Redis processes"""
    print("🔍 Killing existing Redis processes...")
    killed_any = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'redis-server' in proc.info['name'] or any('redis-server' in cmd for cmd in proc.info['cmdline']):
                print(f"💀 Killing Redis process (PID: {proc.info['pid']})")
                proc.kill()
                killed_any = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_any:
        time.sleep(2)  # Wait for processes to fully terminate
        print("✅ Redis processes killed")
    else:
        print("✅ No Redis processes found")


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
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=5)
        r.ping()
        return True
    except Exception:
        return False


def start_redis():
    """Start Redis with proper configuration for Replit/Nix environment"""
    print("🚀 Starting Redis server...")
    
    # Kill any existing Redis processes first
    kill_redis_processes()
    
    # Try multiple Redis startup strategies
    redis_commands = [
        # Strategy 1: Use env LD_PRELOAD= to bypass jemalloc issues
        "env LD_PRELOAD= redis-server --save '' --appendonly no --bind 0.0.0.0 --port 6379 --daemonize yes --maxmemory 100mb --maxmemory-policy allkeys-lru",
        
        # Strategy 2: Use alternative allocator
        "env MALLOC_ARENA_MAX=1 redis-server --save '' --appendonly no --bind 0.0.0.0 --port 6379 --daemonize yes --maxmemory 100mb",
        
        # Strategy 3: Simple Redis with minimal config
        "redis-server --save '' --appendonly no --bind 0.0.0.0 --port 6379 --daemonize yes --maxmemory 50mb"
    ]
    
    for i, redis_cmd in enumerate(redis_commands, 1):
        print(f"📋 Trying Redis startup strategy {i}...")
        print(f"📝 Command: {redis_cmd}")
        
        try:
            result = subprocess.run(redis_cmd, shell=True, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✅ Redis command executed successfully")
                # Wait a moment for Redis to start
                time.sleep(3)
                
                # Check if Redis is actually running
                if is_redis_running():
                    print("✅ Redis is running and responding to pings")
                    return True
                else:
                    print("⚠️ Redis command succeeded but server not responding")
            else:
                print(f"❌ Redis startup failed with return code {result.returncode}")
                if result.stderr:
                    print(f"[REDIS-ERR] {result.stderr}")
                    
        except subprocess.TimeoutExpired:
            print("⚠️ Redis startup command timed out")
        except Exception as e:
            print(f"❌ Redis startup error: {e}")
            
        # If this strategy failed, try the next one
        kill_redis_processes()
        time.sleep(2)
    
    print("❌ All Redis startup strategies failed")
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
    redis_started = False
    if not is_redis_running():
        redis_started = start_redis()
        if not redis_started:
            print("⚠️ Redis failed to start, will run data collection synchronously")
    else:
        print("✅ Redis is already running")
        redis_started = True

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

    # Start Celery components only if Redis is running
    celery_worker_process = None
    celery_beat_process = None
    
    if redis_started:
        # Start Celery worker
        print("🚀 Starting Celery worker...")
        celery_worker_cmd = f"cd {project_root}/backend && celery -A backend worker -l info"
        celery_worker_process = start_service(celery_worker_cmd,
                                              "Celery-Worker",
                                              working_dir=str(project_root / "backend"))
        time.sleep(3)  # Wait for Celery worker to start

        # Start Celery beat
        print("🚀 Starting Celery beat scheduler...")
        celery_beat_cmd = f"cd {project_root}/backend && celery -A backend beat -l info"
        celery_beat_process = start_service(celery_beat_cmd,
                                            "Celery-Beat",
                                            working_dir=str(project_root / "backend"))
        time.sleep(3)  # Wait for Celery beat to start
    else:
        print("⚠️ Skipping Celery services due to Redis issues")
        print("   Data collection will run synchronously when triggered")

    print("\n🎉 Services started!")
    print("=" * 50)
    print("🌐 Django server running at: http://localhost:3000")
    print("🌐 Django admin: http://localhost:3000/admin/")
    print("🌐 Django API: http://localhost:3000/api/")
    print("=" * 50)
    print("📊 Process monitoring:")
    print(f"  - Django PID: {django_process.pid}")
    if redis_started:
        print(f"  - Redis: Running")
        if celery_worker_process:
            print(f"  - Celery Worker PID: {celery_worker_process.pid}")
        if celery_beat_process:
            print(f"  - Celery Beat PID: {celery_beat_process.pid}")
    else:
        print(f"  - Redis: Failed to start (will use sync processing)")
    print("=" * 50)
    print("✋ Press Ctrl+C to stop all services...")

    try:
        # Keep the script running and monitor processes
        while True:
            time.sleep(5)

            # Check if any process died
            processes = [("Django", django_process)]
            
            if celery_worker_process:
                processes.append(("Celery-Worker", celery_worker_process))
            if celery_beat_process:
                processes.append(("Celery-Beat", celery_beat_process))

            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"⚠️ {name} process died with return code: {proc.returncode}")

    except KeyboardInterrupt:
        print("\n🛑 Stopping all services...")

        # Stop all processes gracefully
        processes_to_stop = [("Django", django_process)]
        
        if celery_worker_process:
            processes_to_stop.append(("Celery-Worker", celery_worker_process))
        if celery_beat_process:
            processes_to_stop.append(("Celery-Beat", celery_beat_process))

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

        # Stop Redis
        if redis_started:
            print("🛑 Stopping Redis...")
            kill_redis_processes()

        print("✅ All services stopped.")


if __name__ == "__main__":
    main()
