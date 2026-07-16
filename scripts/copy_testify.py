import os
import shutil
import re

def main():
    # Define paths
    brain_dir = r"C:\Users\zarya\.gemini\antigravity\brain\17afcba3-4e42-4736-95b4-3bd40b9fca07"
    lessons_dir = r"d:\Projects\PORTFOLIO\CORTEXRAG\lessons"
    testify_dir = r"d:\Projects\PORTFOLIO\CORTEXRAG\testify"

    # Create testify directory
    os.makedirs(testify_dir, exist_ok=True)
    print(f"Ensured directory exists: {testify_dir}")

    # Copy global artifacts
    global_mappings = {
        "implementation_plan.md": "00_global_implementation_plan.md",
        "task.md": "00_global_task_tracker.md",
        "walkthrough.md": "00_global_walkthrough.md"
    }

    for src_name, dest_name in global_mappings.items():
        src_path = os.path.join(brain_dir, src_name)
        dest_path = os.path.join(testify_dir, dest_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            print(f"Copied global: {src_name} to {dest_name}")
        else:
            print(f"Warning: Global file not found: {src_path}")

    # Copy index.md
    index_src = os.path.join(lessons_dir, "index.md")
    index_dest = os.path.join(testify_dir, "00_lessons_index.md")
    if os.path.exists(index_src):
        shutil.copy2(index_src, index_dest)
        print("Copied index.md to 00_lessons_index.md")
    else:
        print("Warning: index.md not found in lessons directory")

    # Copy lessons
    copied_count = 0
    for filename in os.listdir(lessons_dir):
        if filename.startswith("step-") and filename.endswith(".md"):
            match = re.match(r"step-(\d+)-(.+)\.md", filename)
            if match:
                num = match.group(1)
                rest = match.group(2).replace("-", "_")
                dest_name = f"{num}_step_{num}_{rest}.md"
                src_path = os.path.join(lessons_dir, filename)
                dest_path = os.path.join(testify_dir, dest_name)
                shutil.copy2(src_path, dest_path)
                copied_count += 1

    print(f"Copied {copied_count} lesson step files.")
    print("Testify compilation complete!")

if __name__ == "__main__":
    main()
