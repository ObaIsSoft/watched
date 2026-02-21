import re

path = '/Users/obafemi/Documents/dev/watchlist/backend/templates/dashboard.html'
with open(path, 'r') as f:
    text = f.read()

# Replace innerHTML assignments that contain "Loading"
text = re.sub(r"innerHTML\s*=\s*'[^']*Loading[^']*';", "innerHTML = getSkeletonGrid(10);", text)
text = re.sub(r'innerHTML\s*=\s*"[^"]*Loading[^"]*";', 'innerHTML = getSkeletonGrid(10);', text)
text = re.sub(r"innerHTML\s*=\s*`[^`]*Loading[^`]*`;", "innerHTML = getSkeletonGrid(10);", text)

with open(path, 'w') as f:
    f.write(text)

print("Replaced loading grids with cinematic skeletons!")
