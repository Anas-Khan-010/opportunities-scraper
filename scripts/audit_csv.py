import csv
import collections

def analyze_csv(file_path):
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    total_rows = len(rows)
    if total_rows == 0:
        print("CSV is empty.")
        return

    # 1. State Coverage
    states = set()
    sources = set()
    source_counts = collections.Counter()
    
    # 2. Field Completeness
    completeness = collections.defaultdict(int)
    fields = ['title', 'organization', 'description', 'eligibility', 'funding_amount', 'deadline', 'document_urls']
    
    # 3. Richness
    rich_desc_count = 0
    comprehensive_count = 0

    for row in rows:
        states.add(row.get('location', 'Unknown'))
        source = row.get('source', 'Unknown')
        sources.add(source)
        source_counts[source] += 1
        
        for field in fields:
            val = row.get(field, '')
            if val and str(val).strip() and str(val).lower() != 'none':
                completeness[field] += 1
        
        desc = row.get('description', '')
        if len(desc) > 200:
            rich_desc_count += 1
            
        if row.get('funding_amount') and row.get('deadline'):
            comprehensive_count += 1

    print(f"Total Opportunities: {total_rows}")
    print(f"\nStates Covered ({len(states)}):")
    print(", ".join(sorted([str(s) for s in states if s])))
    
    print("\nField Completeness (%):")
    for f in fields:
        pct = (completeness[f] / total_rows) * 100
        print(f"  {f:15}: {pct:.2f}%")
        
    print(f"\nRichness Metrics:")
    print(f"  Rich Descriptions (>200 chars): {(rich_desc_count/total_rows)*100:.2f}%")
    print(f"  Comprehensive (Funding + Deadline): {(comprehensive_count/total_rows)*100:.2f}%")
    
    print("\nTop Sources:")
    for source, count in source_counts.most_common(20):
        print(f"  {source:25}: {count}")

if __name__ == "__main__":
    analyze_csv('opportunities_rows (1).csv')
