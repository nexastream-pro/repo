import os
import hashlib

def generate_repo():
    addons_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<addons>\n"
    
    # Projde všechny složky v aktuálním adresáři
    for dir_name in os.listdir('.'):
        if os.path.isdir(dir_name) and not dir_name.startswith('.'):
            xml_path = os.path.join(dir_name, 'addon.xml')
            
            if os.path.exists(xml_path):
                print(f"Zpracovávám: {dir_name}")
                with open(xml_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Odstraní XML hlavičku, pokud tam je
                    content = content.replace('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '')
                    content = content.replace('<?xml version="1.0" encoding="UTF-8"?>', '')
                    addons_xml += content.strip() + "\n\n"
    
    addons_xml += "</addons>"
    
    # Uložení addons.xml
    with open('addons.xml', 'w', encoding='utf-8') as f:
        f.write(addons_xml)
    
    # Výpočet MD5 hashe
    md5_hash = hashlib.md5(addons_xml.encode('utf-8')).hexdigest()
    
    # Uložení addons.xml.md5
    with open('addons.xml.md5', 'w', encoding='utf-8') as f:
        f.write(md5_hash)
        
    print("-" * 30)
    print("HOTOVO!")
    print(f"Nový MD5: {md5_hash}")
    print("Teď můžeš soubory nahrát na GitHub.")

if __name__ == "__main__":
    generate_repo()