"""Test Local Storage Service"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.local_storage import db_service

print('='*60)
print('Local Storage Service Test')
print('='*60)

# Test 1: Get status
print('\n1. Testing get_status()...')
status = db_service.get_status()
print(f'   Status: {status}')
assert status['status'] == 'online', 'Status should be online'
assert status['type'] == 'local_storage', 'Type should be local_storage'
print('   ✓ PASSED')

# Test 2: Insert data
print('\n2. Testing insert_one()...')
test_data = {
    'user_id': 'Agri_1',
    'soil_name': 'Red Soil',
    'test_field': 'test_value'
}
result = db_service.insert_one('soil_results', test_data)
print(f'   Inserted ID: {result.inserted_id}')
assert result.inserted_id is not None, 'Should have inserted ID'
print('   ✓ PASSED')

# Test 3: Find data
print('\n3. Testing find_one()...')
found = db_service.find_one('soil_results', {'user_id': 'Agri_1'})
print(f'   Found: {found}')
assert found is not None, 'Should find the record'
assert found['soil_name'] == 'Red Soil', 'Should have correct soil_name'
print('   ✓ PASSED')

# Test 4: Update data
print('\n4. Testing update_one()...')
update_result = db_service.update_one(
    'soil_results',
    {'user_id': 'Agri_1'},
    {'$set': {'soil_name': 'Black Soil'}}
)
print(f'   Modified count: {update_result.modified_count}')
found = db_service.find_one('soil_results', {'user_id': 'Agri_1'})
assert found['soil_name'] == 'Black Soil', 'Should have updated soil_name'
print('   ✓ PASSED')

# Test 5: Find all data
print('\n5. Testing find()...')
all_results = db_service.find('soil_results', {'user_id': 'Agri_1'})
print(f'   Found {len(all_results)} records')
assert len(all_results) > 0, 'Should find records'
print('   ✓ PASSED')

# Test 6: Delete data
print('\n6. Testing delete_one()...')
delete_result = db_service.delete_one('soil_results', {'user_id': 'Agri_1'})
print(f'   Deleted count: {delete_result.deleted_count}')
assert delete_result.deleted_count == 1, 'Should delete 1 record'
print('   ✓ PASSED')

# Test 7: Verify deletion
print('\n7. Verifying deletion...')
found = db_service.find_one('soil_results', {'user_id': 'Agri_1'})
print(f'   Found after delete: {found}')
assert found is None, 'Record should be deleted'
print('   ✓ PASSED')

# Test 8: Count documents
print('\n8. Testing count_documents()...')
count = db_service.count_documents('soil_results')
print(f'   Count: {count}')
print('   ✓ PASSED')

print('\n' + '='*60)
print('ALL LOCAL STORAGE TESTS PASSED!')
print('='*60)
print('\nMongoDB successfully replaced with Local JSON Storage!')
print(f'Data directory: {status["path"]}')
