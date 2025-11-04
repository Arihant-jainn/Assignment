import PyPDF2
import re
import csv
from typing import List, Dict, Tuple
import spacy
import warnings
warnings.filterwarnings('ignore')

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"  Total pages: {len(pdf_reader.pages)}")
            for i, page in enumerate(pdf_reader.pages, 1):
                print(f"  Processing page {i}...", end='\r')
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def extract_pan_numbers(text: str) -> List[str]:
    """Extract PAN numbers using regex pattern."""
    # PAN format: 5 letters, 4 digits, 1 letter
    pan_pattern = r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'
    pans = re.findall(pan_pattern, text.upper())
    return list(set(pans))  # Remove duplicates

def find_context_around_pan(text: str, pan: str, window: int = 150) -> str:
    """Extract context around PAN number for better entity matching."""
    pattern = re.compile(re.escape(pan), re.IGNORECASE)
    match = pattern.search(text)
    
    if match:
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        return text[start:end]
    return ""

def extract_person_names(text: str, nlp) -> List[str]:
    """Extract person names using spaCy NER."""
    doc = nlp(text)
    persons = []
    
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            # Clean the name
            name = ent.text.strip()
            # Filter out single characters and common false positives
            if len(name) > 2 and not name.isdigit():
                persons.append(name)
    
    return persons

def extract_organizations(text: str, nlp) -> List[str]:
    """Extract organization names using spaCy NER."""
    doc = nlp(text)
    orgs = []
    
    for ent in doc.ents:
        if ent.label_ == "ORG":
            org = ent.text.strip()
            if len(org) > 2 and not org.isdigit():
                orgs.append(org)
    
    return orgs

def find_nearest_entity(pan: str, context: str, persons: List[str], orgs: List[str]) -> Tuple[str, str]:
    """Find the nearest person or organization to the PAN number."""
    context_lower = context.lower()
    pan_pos = context_lower.find(pan.lower())
    
    if pan_pos == -1:
        return None, None
    
    # Find closest entity (person or org)
    closest_entity = None
    closest_distance = float('inf')
    entity_type = None
    
    # Check persons
    for person in persons:
        pos = context_lower.find(person.lower())
        if pos != -1:
            distance = abs(pos - pan_pos)
            if distance < closest_distance:
                closest_distance = distance
                closest_entity = person
                entity_type = "Person"
    
    # Check organizations
    for org in orgs:
        pos = context_lower.find(org.lower())
        if pos != -1:
            distance = abs(pos - pan_pos)
            if distance < closest_distance:
                closest_distance = distance
                closest_entity = org
                entity_type = "Organisation"
    
    return closest_entity, entity_type

def extract_with_patterns(text: str, pan: str) -> Tuple[str, str]:
    """Use pattern matching to find PAN relationships."""
    # Common patterns in documents
    patterns = [
        # "PAN: XXXXX of Mr./Ms./Mrs. Name"
        (r'(?:PAN|Pan|pan)[\s:]+' + re.escape(pan) + r'\s+(?:of|for|belonging to|issued to)\s+(?:Mr\.|Ms\.|Mrs\.|Dr\.|Shri|Smt\.)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', 'Person'),
        # "Mr./Ms. Name (PAN: XXXXX)"
        (r'(?:Mr\.|Ms\.|Mrs\.|Dr\.|Shri|Smt\.)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:\(|,|\s)(?:PAN|Pan|pan)[\s:]*' + re.escape(pan), 'Person'),
        # "Company Name - PAN: XXXXX"
        (r'([A-Z][A-Za-z\s&,\.]+?(?:Ltd|Limited|Pvt|Private|Corporation|Corp|Inc|Company|Enterprises|Industries))\s*(?:-|–|:|,)?\s*(?:PAN|Pan|pan)[\s:]*' + re.escape(pan), 'Organisation'),
        # "PAN XXXXX in the name of Company"
        (r'(?:PAN|Pan|pan)[\s:]*' + re.escape(pan) + r'\s+(?:in the name of|belongs to|for)\s+([A-Z][A-Za-z\s&,\.]+?(?:Ltd|Limited|Pvt|Private|Corporation|Corp|Inc|Company|Enterprises|Industries))', 'Organisation'),
    ]
    
    for pattern, entity_type in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), entity_type
    
    return None, None

def process_entities(text: str) -> List[Dict]:
    """Main processing function to extract entities and relations."""
    print("\n[2] Loading spaCy model (lightweight)...")
    try:
        nlp = spacy.load("en_core_web_sm")
    except:
        print("  spaCy model not found. Downloading...")
        import os
        os.system("python -m spacy download en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")
    
    print("\n[3] Extracting PAN numbers...")
    pan_numbers = extract_pan_numbers(text)
    print(f"  Found {len(pan_numbers)} PAN numbers")
    
    if not pan_numbers:
        print("  No PAN numbers found in the document!")
        return []
    
    print("\n[4] Extracting entities and building relations...")
    entities = []
    
    for idx, pan in enumerate(pan_numbers, 1):
        print(f"  Processing PAN {idx}/{len(pan_numbers)}: {pan}")
        
        # Get context around PAN
        context = find_context_around_pan(text, pan, window=200)
        
        # Try pattern matching first (most accurate)
        entity_name, entity_type = extract_with_patterns(text, pan)
        
        # If pattern matching fails, use NER
        if not entity_name:
            persons = extract_person_names(context, nlp)
            orgs = extract_organizations(context, nlp)
            entity_name, entity_type = find_nearest_entity(pan, context, persons, orgs)
        
        # If still no match, try broader context
        if not entity_name:
            broader_context = find_context_around_pan(text, pan, window=400)
            persons = extract_person_names(broader_context, nlp)
            orgs = extract_organizations(broader_context, nlp)
            entity_name, entity_type = find_nearest_entity(pan, broader_context, persons, orgs)
        
        # Store the result
        if entity_name:
            entities.append({
                'entity_type': 'PAN',
                'value': pan,
                'relation': 'PAN_Of',
                'related_entity_type': entity_type,
                'related_entity': entity_name
            })
            print(f"    → Linked to: {entity_name} ({entity_type})")
        else:
            # Store unmatched PANs
            entities.append({
                'entity_type': 'PAN',
                'value': pan,
                'relation': 'PAN_Of',
                'related_entity_type': 'Unknown',
                'related_entity': 'Not Found'
            })
            print(f"    → Could not find related entity")
    
    return entities

def save_to_csv(entities: List[Dict], output_path: str):
    """Save extracted entities and relations to CSV file."""
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Entity_Type', 'Entity_Value', 'Relation', 'Related_Entity_Type', 'Related_Entity']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for entity in entities:
            writer.writerow({
                'Entity_Type': entity.get('entity_type', ''),
                'Entity_Value': entity.get('value', ''),
                'Relation': entity.get('relation', ''),
                'Related_Entity_Type': entity.get('related_entity_type', ''),
                'Related_Entity': entity.get('related_entity', '')
            })
    
    print(f"\n✓ Results saved to {output_path}")

def main():
    # Configuration
    pdf_path = "PDF for Python LLM (1).pdf"
    output_csv = "extracted_entities.csv"
    
    print("="*70)
    print(" Entity and Relation Extraction System (Lightweight Version)")
    print("="*70)
    
    # Step 1: Extract text from PDF
    print("\n[1] Extracting text from PDF...")
    text = extract_text_from_pdf(pdf_path)
    
    if not text:
        print("❌ Error: No text extracted from PDF!")
        return
    
    print(f"\n  ✓ Extracted {len(text)} characters from PDF")
    
    # Step 2-4: Process entities
    entities = process_entities(text)
    
    # Step 5: Save to CSV
    print("\n[5] Saving results to CSV...")
    save_to_csv(entities, output_csv)
    
    # Display summary
    print("\n" + "="*70)
    print(" EXTRACTION SUMMARY")
    print("="*70)
    print(f"Total PAN numbers found: {len(entities)}")
    
    matched = sum(1 for e in entities if e['related_entity'] != 'Not Found')
    print(f"Successfully matched: {matched}")
    print(f"Unmatched: {len(entities) - matched}")
    
    print("\n📋 Sample results:")
    print("-"*70)
    for i, entity in enumerate(entities[:10], 1):
        status = "✓" if entity['related_entity'] != 'Not Found' else "✗"
        print(f"{status} {i}. PAN: {entity.get('value')}")
        print(f"   → Belongs to: {entity.get('related_entity')} ({entity.get('related_entity_type')})")
        print()
    
    if len(entities) > 10:
        print(f"... and {len(entities) - 10} more entities")
    
    print("="*70)
    print(f"✓ COMPLETE! Check '{output_csv}' for full results")
    print("="*70)

if __name__ == "__main__":
    main()