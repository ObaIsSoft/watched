fetch("http://localhost:8000/api/public/stats/1").then(r=>r.json()).then(stats=>{
    const rawData = Object.fromEntries(
        Object.entries(stats.country_distribution || {}).filter(([k]) => k && k.trim() !== '' && k.length === 2)
    );
    console.log("Map Countries:", Object.keys(rawData).length);
    console.log("Critic Curve length:", stats.rating_curve?.length);
}).catch(console.error);
