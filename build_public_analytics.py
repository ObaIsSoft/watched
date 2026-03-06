from bs4 import BeautifulSoup

with open("backend/templates/dashboard.html", "r") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Get head
head_content = str(soup.head)

# Get standard public header (from playlist)
header = """
<div class="flex justify-between items-center mb-8 px-4 md:px-8 mt-8 max-w-7xl mx-auto">
    <div class="flex items-center gap-3">
        <div class="bg-indigo-600 p-2 rounded-lg">
            <i data-lucide="bar-chart-2" class="w-6 h-6 text-white"></i>
        </div>
        <span class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
            {{ user.name }}'s Cinema Stats
        </span>
    </div>
    <a href="/" class="bg-indigo-600 hover:bg-indigo-500 px-6 py-2 rounded-lg font-bold transition-all hover:scale-105 shadow-lg shadow-indigo-500/20">
        Create Your Own
    </a>
</div>
"""

# Extract analytics div
analytics_div = soup.find(id="tab-analytics")
if analytics_div:
    # Ensure it's not hidden
    if "hidden" in analytics_div.get("class", []):
        analytics_div["class"].remove("hidden")
    analytics_content = str(analytics_div)
else:
    analytics_content = "<!-- Analytics Not Found -->"

body_wrapper = f"""
<body class="min-h-screen pb-12 selection:bg-indigo-500/30" style="background-color: #0f172a; color: white;">
    {header}
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
        {analytics_content}
    </div>
"""

# Find the script that contains initPhase2Charts
scripts = soup.find_all("script")
chart_script = ""
for s in scripts:
    if s.string and "async function initPhase2Charts" in s.string:
        st = s.string
        start_idx = st.find("async function initPhase2Charts")
        end_idx = st.find("function renderRecommendationSlides")
        if end_idx == -1:
            end_idx = len(st)
        chart_script = st[start_idx:end_idx]
        break

custom_js = f"""
<script>
    lucide.createIcons();
    
    document.addEventListener("DOMContentLoaded", async () => {{
        try {{
            const res = await fetch(`/api/public/stats/{{{{ user.id }}}}`);
            if (res.ok) {{
                const stats = await res.json();
                console.log("Public Stats:", stats);
                await initPhase2Charts(stats);
            }} else {{
                console.error("Failed to load stats");
            }}
        }} catch(e) {{
            console.error(e);
        }}
    }});
    
{chart_script}
</script>
</body>
</html>
"""

final = f"<!DOCTYPE html>\n<html lang='en'>\n{head_content}\n{body_wrapper}\n{custom_js}"

with open("backend/templates/analytics_public.html", "w") as f:
    f.write(final)

print("Generated analytics_public.html successfully")
