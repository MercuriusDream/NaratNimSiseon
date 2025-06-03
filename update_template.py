
import json
import os
import re

def update_template():
    # Path to the asset manifest
    manifest_path = 'frontend/build/asset-manifest.json'
    template_path = 'backend/templates/index.html'
    
    if not os.path.exists(manifest_path):
        print("Asset manifest not found. Make sure to build the frontend first.")
        return
    
    if not os.path.exists(template_path):
        print("Template file not found.")
        return
    
    # Read the asset manifest
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Extract CSS and JS file names
    css_file = manifest['files'].get('main.css', '').replace('/static/', '')
    js_file = manifest['files'].get('main.js', '').replace('/static/', '')
    
    if not css_file or not js_file:
        print("Could not find main CSS or JS files in manifest")
        return
    
    # Read the current template
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # Update CSS reference
    template_content = re.sub(
        r'<link href="[^"]*main\.[^"]*\.css[^"]*" rel="stylesheet">',
        f'<link href="{{% static \'{css_file}\' %}}" rel="stylesheet">',
        template_content
    )
    
    # Update JS reference
    template_content = re.sub(
        r'<script src="[^"]*main\.[^"]*\.js[^"]*"></script>',
        f'<script src="{{% static \'{js_file}\' %}}"></script>',
        template_content
    )
    
    # Write the updated template
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    print(f"Updated template with CSS: {css_file}, JS: {js_file}")

if __name__ == '__main__':
    update_template()
