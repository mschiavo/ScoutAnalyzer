sample_file = r"D:\Volley\B1FB\giornata_01\&01_COR-VOL_Vicenza_b1fb_26_s.dvw"

with open(sample_file, 'r', encoding='latin-1') as f:
    lines = [l.strip() for l in f if l.strip()]

scout_lines = []
is_scout = False
for l in lines:
    if l.startswith('[3SCOUT]'):
        is_scout = True
        continue
    elif l.startswith('[') and is_scout:
        break
    if is_scout:
        scout_lines.append(l)

# Cerchiamo la riga che apre il Set 4 (es. codice >LUp o simile)
for idx, l in enumerate(scout_lines):
    if idx > 1150 and ('>LUp' in l or '>LUP' in l):
        for offset in range(0, 10):
            p = scout_lines[idx + offset].split(';')
            print(f"[{idx + offset + 1:4d}] {p[0]:<15} | Home Pos: {p[14:20]} | Away Pos: {p[20:26]}")
        break
