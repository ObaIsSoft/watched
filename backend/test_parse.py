crew_str = "James Cameron, Rae Sanchini"
if crew_str.strip().startswith('['):
    pass
else:
    for c in crew_str.split(','):
        c = c.strip()
        if c: 
            print(c)
