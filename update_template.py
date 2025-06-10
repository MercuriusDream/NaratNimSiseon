import os
import re
from pathlib import Path

def update_template():
    # Path to the built React app
    build_dir = Path('frontend/build')
    static_dir = build_dir / 'static'

    # Path to Django template
    template_path = Path('backend/templates/index.html')

    if not build_dir.exists():
        print("❌ Build directory not found. Run 'npm run build' first.")
        return

    # Read the original index.html from React build
    original_html = (build_dir / 'index.html').read_text()

    # Find CSS and JS files
    css_files = list((static_dir / 'css').glob('main.*.css'))
    js_files = list((static_dir / 'js').glob('main.*.js'))

    if not css_files or not js_files:
        print("❌ CSS or JS files not found in build/static")
        return

    # Get the latest files (sorted by modification time)
    latest_css = max(css_files, key=os.path.getmtime)
    latest_js = max(js_files, key=os.path.getmtime)

    css_filename = latest_css.name
    js_filename = latest_js.name

    print(f"📁 Found CSS: {css_filename}")
    print(f"📁 Found JS: {js_filename}")

    # Read the current template
    with open(template_path, 'r') as f:
        template_content = f.read()

    # Update CSS reference
    template_content = re.sub(
        r'<link href="[^"]*main\.[^"]*\.css[^"]*" rel="stylesheet">',
        f'<link href="{{% static \'static/css/{css_filename}\' %}}" rel="stylesheet">',
        template_content
    )

    # Update JS reference
    template_content = re.sub(
        r'<script src="[^"]*main\.[^"]*\.js[^"]*"></script>',
        f'<script src="{{% static \'static/js/{js_filename}\' %}}"></script>',
        template_content
    )

    # Write the updated template
    with open(template_path, 'w') as f:
        f.write(template_content)

    print(f"✅ Updated template with CSS: static/css/{css_filename}, JS: static/js/{js_filename}")

if __name__ == '__main__':
    update_template()