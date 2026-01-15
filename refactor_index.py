import os

filepath = 'frontend/index.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Markers
start_marker = '<div class="view-stack" style="padding: 0 20px; position: relative;">'
end_marker = '<!-- GLOBAL FOOTER (Terminal Logs) -->'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"Could not find markers! Start: {start_idx}, End: {end_idx}")
    # Fallback to try finding the line we saw in grep if exact string match fails due to spaces
    start_alt = 'class="view-stack"'
    start_idx = content.find(start_alt)
    if start_idx != -1:
        # Backtrack to start of line
        start_idx = content.rfind('<', 0, start_idx)
    else:
        exit(1)

# Construct new content
# We replace everything from start_idx up to the footer, and insert the new clean view-stack div.
# Note: The original file had the closing </div> for view-stack just before the footer.
# We will regenerate that closing div in our new section.

new_section = '''        <div class="view-stack" style="padding: 0 20px; position: relative;">
            <!-- Views are loaded dynamically from /templates -->
        </div>

        '''

# We slice content[:start_idx] (keep everything before view-stack)
# We append new_section
# We append content[end_idx:] (keep everything from footer onwards)

new_content = content[:start_idx] + new_section + content[end_idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Successfully refactored index.html")
