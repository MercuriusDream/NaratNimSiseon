
import os
import re
import glob

def update_django_template():
    # Find the latest CSS and JS files
    css_files = glob.glob('backend/staticfiles/css/main.*.css')
    js_files = glob.glob('backend/staticfiles/js/main.*.js')
    
    if not css_files or not js_files:
        print("No CSS or JS files found!")
        return
    
    # Get the latest files (assuming they're the ones we want)
    latest_css = os.path.basename(css_files[0])
    latest_js = os.path.basename(js_files[0])
    
    # Read the template file
    template_path = 'backend/templates/index.html'
    with open(template_path, 'r') as f:
        content = f.read()
    
    # Update CSS reference
    content = re.sub(
        r'<link href="{% static \'static/css/main\.[^\']+\.css\' %}" rel="stylesheet">',
        f'<link href="{{% static \'static/css/{latest_css}\' %}}" rel="stylesheet">',
        content
    )
    
    # Update JS reference
    content = re.sub(
        r'<script src="{% static \'static/js/main\.[^\']+\.js\' %}"></script>',
        f'<script src="{{% static \'static/js/{latest_js}\' %}}"></script>',
        content
    )
    
    # Write back to file
    with open(template_path, 'w') as f:
        f.write(content)
    
    print(f"Updated template with CSS: {latest_css}, JS: {latest_js}")

if __name__ == "__main__":
    update_django_template()
