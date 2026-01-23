"""
Seed test team members for routing tests.
Adds Mayank (DEV) and Zea (ADMIN) to the database.
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import get_database
from src.database.repositories import get_team_repository

async def seed_test_team():
    """Seed Mayank and Zea for routing tests."""
    
    # Initialize database
    db = get_database()
    await db.initialize()
    
    team_repo = get_team_repository()
    
    # Test team members for routing tests
    test_members = [
        {
            "name": "Mayank",
            "role": "Developer",  # Maps to DEV category
            "telegram_id": "123456789",  # Fake ID for testing
            "discord_id": "987654321",  # Fake ID for testing
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "is_active": True
        },
        {
            "name": "Zea",
            "role": "Admin",  # Maps to ADMIN category  
            "telegram_id": "111111111",  # Fake ID for testing
            "discord_id": "222222222",  # Fake ID for testing
            "skills": ["Management", "Coordination"],
            "is_active": True
        }
    ]
    
    print("Seeding test team members...")
    for member_data in test_members:
        try:
            # Check if exists
            existing = await team_repo.find_member(member_data["name"])
            if existing:
                print(f"  ✅ {member_data['name']} already exists with role: {existing.role}")
                # Update role if needed
                if existing.role != member_data["role"]:
                    await team_repo.update(existing.id, {"role": member_data["role"]})
                    print(f"     Updated role to: {member_data['role']}")
            else:
                # Create new
                created = await team_repo.create(member_data)
                print(f"  ✅ Created {member_data['name']} with role: {member_data['role']} (ID: {created.id})")
        except Exception as e:
            print(f"  ❌ Error seeding {member_data['name']}: {e}")
    
    # Verify
    print("\nVerifying team members...")
    all_members = await team_repo.get_all()
    print(f"Total team members: {len(all_members)}")
    for member in all_members:
        print(f"  - {member.name}: {member.role}")
    
    print("\n✅ Test team seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_test_team())
