import React, { useState, useEffect } from 'react';
import BillCard from './BillCard';
import api from '../api'; // Import the axios instance
import { ENDPOINTS } from '../apiConfig'; // Import endpoint paths

const BillList = ({ filter = 'all', searchTerm = '', selectedCategory = null }) => {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBills = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await api.get(ENDPOINTS.BILLS);
        setBills(response.data);
      } catch (err) {
        const message = err.response?.data?.message || err.response?.data?.detail || err.message || '의안 목록을 불러오는데 실패했습니다.';
        setError(message);
        console.error('Error fetching bills:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchBills();
  }, [filter]);

  const billsArray = Array.isArray(bills) ? bills : 
                    (bills?.data && Array.isArray(bills.data)) ? bills.data : 
                    (bills?.results && Array.isArray(bills.results)) ? bills.results : [];

  const filteredBills = billsArray.filter(bill => {
    const matchesSearch = searchTerm === '' || 
                         bill.bill_nm?.toLowerCase().includes(searchTerm.toLowerCase()) || 
                         bill.session?.era_co?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesCategory = !selectedCategory || 
                          bill.categories?.some(cat => cat.category.id === parseInt(selectedCategory));

    const matchesFilter = filter === 'all' || bill.status === filter;

    return matchesSearch && matchesCategory && matchesFilter;
  });

  if (loading) {
    return (
      <section className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">의안 목록을 불러오는 중...</p>
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <p className="text-red-600">{error}</p>
            <button onClick={() => window.location.reload()} className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">다시 시도</button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="py-20 bg-white">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold text-gray-900 mb-6">대표 의안 목록</h2>
          <p className="text-xl text-gray-600 mb-12">
            각 의안에 대한 기본 정보와 입장 변화를 확인할 수 있습니다.
          </p>

          {filteredBills.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600">표시할 의안이 없습니다.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {filteredBills.map(bill => (
                <BillCard
                  key={bill.bill_id}
                  id={bill.bill_id}
                  number={bill.bill_id}
                  title={bill.bill_nm}
                  description={bill.summary || '의안 요약이 제공되지 않았습니다.'}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default BillList;