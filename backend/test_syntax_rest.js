const fs = require('fs');
const acorn = require('acorn');

['templates/export_public.html', 'templates/playlist_public.html'].forEach(file => {
    console.log("Checking:", file);
    const html = fs.readFileSync(file, 'utf8');
    const parts = html.split('<script>');
    parts.shift(); // remove everything before first script
    parts.forEach(part => {
        const scriptEnd = part.indexOf('</script>');
        if (scriptEnd !== -1) {
            const jsCode = part.substring(0, scriptEnd);
            // Skip json scripts or module scripts if they exist, though we mainly care about our logic
            if (jsCode.trim() && !jsCode.includes('tailwindcss.com')) {
                try {
                    // Try parsing as normal script
                    acorn.parse(jsCode, { ecmaVersion: 2022, sourceType: 'module' });
                } catch (e) {
                     // Since Jinja {{ var }} syntax breaks pure JS parsers, we might see errors, but we can look at what they are.
                    console.log(`  Potential issue around line ${e.loc?.line}: ${e.message}`);
                }
            }
        }
    });
});
