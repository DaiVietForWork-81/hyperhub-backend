import asyncio
import pytest
from services.knowledge_base import kb

@pytest.mark.asyncio
async def test_knowledge_base_smoke():
    # Test ingest
    r = await kb.ingest_text('Python la ngon ngu lap trinh bac cao. Dung cho AI, web, data science.', 'python_intro', 'text')
    print('Ingest:', r)
    
    # Test search
    r = await kb.search('Python ngon ngu')
    print('Search:', len(r), 'results')
    for item in r:
        print(f'  - {item["source_name"]}: {item["content"][:80]}...')
    
    # Test context
    ctx = await kb.get_context_for_query('Python dung lam gi')
    print('Context:', ctx[:200])
    
    # Stats
    stats = await kb.stats()
    print('Stats:', stats)

if __name__ == "__main__":
    asyncio.run(test_knowledge_base_smoke())