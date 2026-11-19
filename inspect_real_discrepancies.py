file_path = r"D:\Volley\B1FB\giornata_01\&01_COR-VOL_Vicenza_b1fb_26_s.dvw"

with open(file_path, 'r', encoding='latin-1') as f:
    lines = [l.strip() for l in f if l.strip()]

scout_lines = [l for l in lines if not l.startswith('[') and ';' in l]

# 1. Cerchiamo dove compare il codice 'a05SM-~~~16C'
print("=== CASO 1: Ricerca di a05SM-~~~16C nel file reale ===")
for idx, l in enumerate(scout_lines):
    if 'a05SM-~~~16C' in l:
        print(f"Trovato alla riga scout: {idx+1}")
        for offset in range(-6, 7):
            cur_idx = idx + offset
            if 0 <= cur_idx < len(scout_lines):
                parts = scout_lines[cur_idx].split(';')
                print(f"[{cur_idx+1:4d}] {parts[0]:<18} | Set:{parts[8]} | Home Pos: {parts[14:20]} | Away Pos: {parts[20:26]}")
        break

print("\n=== CASO 5: Ricerca di *04SM+~~~57A nel file reale ===")
for idx, l in enumerate(scout_lines):
    if '*04SM+~~~57A' in l:
        print(f"Trovato alla riga scout: {idx+1}")
        for offset in range(-6, 7):
            cur_idx = idx + offset
            if 0 <= cur_idx < len(scout_lines):
                parts = scout_lines[cur_idx].split(';')
                print(f"[{cur_idx+1:4d}] {parts[0]:<18} | Set:{parts[8]} | Home Pos: {parts[14:20]} | Away Pos: {parts[20:26]}")
        break
