
import os
import sys

filepath = 'main_window_qt.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if 'selected_paths = []' in line and 'selected_policy = "detect_only"' in lines[i+1]:
        new_lines.append(line)
        new_lines.append('            selected_policy = "detect_only"\n')
        new_lines.append('            include_all_screenshot_faces = False\n')
        skip = True
        continue
    if skip and 'def on_scope_selected(paths, policy):' in line:
        new_lines.append('            def on_scope_selected(paths, policy, include_all_flag):\n')
        new_lines.append('                nonlocal selected_paths, selected_policy, include_all_screenshot_faces\n')
        new_lines.append('                selected_paths = paths\n')
        new_lines.append('                selected_policy = policy\n')
        new_lines.append('                include_all_screenshot_faces = bool(include_all_flag)\n')
        skip = False
        continue
    if skip and ('selected_policy = "detect_only"' in line or 'nonlocal selected_paths, selected_policy' in line or 'selected_paths = paths' in line or 'selected_policy = policy' in line):
        continue

    if 'started = svc.start(' in line and 'project_id=project_id,' in lines[i+1]:
        new_lines.append(line)
        new_lines.append('                project_id=project_id,\n')
        new_lines.append('                photo_paths=selected_paths,\n')
        new_lines.append('                screenshot_policy=selected_policy,\n')
        new_lines.append('                include_all_screenshot_faces=include_all_screenshot_faces,\n')
        skip_start = True
        continue

    if 'started = svc.start(' in line:
        # Check for single line version
        if 'screenshot_policy=selected_policy' in line:
             new_line = line.replace('screenshot_policy=selected_policy', 'screenshot_policy=selected_policy, include_all_screenshot_faces=include_all_screenshot_faces')
             new_lines.append(new_line)
             continue

    if 'started = svc.start(' in line:
         new_lines.append(line)
         continue

    new_lines.append(line)

# Second pass for the start call if multi-line
final_lines = []
skip_until_paren = False
for line in new_lines:
    if 'started = svc.start(' in line and 'include_all_screenshot_faces=include_all_screenshot_faces' in line:
        final_lines.append(line)
        skip_until_paren = True
        continue
    if skip_until_paren:
        if ')' in line:
            skip_until_paren = False
            # We already added the args, so just skip
        continue
    final_lines.append(line)

with open(filepath, 'w') as f:
    f.writelines(final_lines)
print("MainWindow patched")
