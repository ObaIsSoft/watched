const fs = require('fs');
const acorn = require('acorn');

const html = fs.readFileSync('templates/analytics_public.html', 'utf8');
const scriptStart = html.lastIndexOf('<script>');
const scriptEnd = html.lastIndexOf('</script>');

if (scriptStart !== -1 && scriptEnd !== -1) {
    const jsCode = html.substring(scriptStart + 8, scriptEnd);
    try {
        acorn.parse(jsCode, { ecmaVersion: 2022, sourceType: 'module' });
        console.log("Syntax is OK.");
    } catch (e) {
        console.error("Syntax Error found!");
        console.error(e.message);
        console.error("At relative line:", e.loc?.line);
        const lines = jsCode.split('\n');
        const start = Math.max(0, (e.loc?.line || 0) - 5);
        const end = Math.min(lines.length, (e.loc?.line || 0) + 5);
        for(let i = start; i < end; i++) {
           console.log(`${i+1}: ${lines[i]}`);
        }
    }
} else {
    console.log("Could not find script block.");
}
