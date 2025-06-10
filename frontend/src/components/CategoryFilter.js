
import React, { useState, useEffect } from 'react';
import api from '../api';

const CategoryFilter = ({ onCategoryChange, selectedCategories = [] }) => {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedCategories, setExpandedCategories] = useState(new Set());

  useEffect(() => {
    fetchCategories();
  }, []);

  const fetchCategories = async () => {
    try {
      const response = await api.get('/categories/');
      const categoriesData = response.data.results || response.data || [];
      // Ensure we always have an array
      setCategories(Array.isArray(categoriesData) ? categoriesData : []);
    } catch (error) {
      console.error('Error fetching categories:', error);
      setCategories([]); // Set empty array on error
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (categoryId) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(categoryId)) {
      newExpanded.delete(categoryId);
    } else {
      newExpanded.add(categoryId);
    }
    setExpandedCategories(newExpanded);
  };

  const handleCategorySelect = (categoryId, subcategoryId = null) => {
    const newSelection = [...selectedCategories];
    const selectionKey = subcategoryId ? `${categoryId}-${subcategoryId}` : categoryId.toString();
    
    if (newSelection.includes(selectionKey)) {
      const index = newSelection.indexOf(selectionKey);
      newSelection.splice(index, 1);
    } else {
      newSelection.push(selectionKey);
    }
    
    onCategoryChange(newSelection);
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded mb-2"></div>
          <div className="h-4 bg-gray-200 rounded mb-2"></div>
          <div className="h-4 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold mb-4">카테고리 필터</h3>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {Array.isArray(categories) && categories.map(category => (
          <div key={category.id} className="border rounded-lg">
            <div className="flex items-center justify-between p-3">
              <label className="flex items-center space-x-2 flex-1">
                <input
                  type="checkbox"
                  checked={selectedCategories.includes(category.id.toString())}
                  onChange={() => handleCategorySelect(category.id)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm font-medium">{category.name}</span>
              </label>
              <button
                onClick={() => toggleCategory(category.id)}
                className="text-gray-400 hover:text-gray-600"
              >
                {expandedCategories.has(category.id) ? '−' : '+'}
              </button>
            </div>
            
            {expandedCategories.has(category.id) && category.subcategories && (
              <div className="px-6 pb-3 space-y-2">
                {category.subcategories.map(subcategory => (
                  <label key={subcategory.id} className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={selectedCategories.includes(`${category.id}-${subcategory.id}`)}
                      onChange={() => handleCategorySelect(category.id, subcategory.id)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-600">{subcategory.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      
      {selectedCategories.length > 0 && (
        <div className="mt-4 pt-4 border-t">
          <button
            onClick={() => onCategoryChange([])}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            모든 필터 해제
          </button>
        </div>
      )}
    </div>
  );
};

export default CategoryFilter;
