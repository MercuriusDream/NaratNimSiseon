import React, { useState, useEffect } from 'react';
import BillCard from './BillCard';
import api from '../api'; // Import the axios instance
import { ENDPOINTS } from '../apiConfig'; // Import endpoint paths

const BillList = ({ filter = 'all' }) => {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBills = async () => {
      try {
        setLoading(true);
        setError(null); // Clear previous errors
        // Construct URL for bills, potentially with query params if 'filter' is used for backend filtering
        // For now, assuming 'filter' is only for client-side, or backend pagination handles 'all'
        // TODO: If 'filter' prop is meant for backend, pass it as params: api.get(ENDPOINTS.BILLS, { params: { status: filter } })
        const response = await api.get(ENDPOINTS.BILLS);
        // Axios wraps the response in a `data` object.
        // DRF paginated responses have results in `response.data.results`
        setBills(response.data.results || response.data || []);
      } catch (err) {
        // Axios errors have a `response` object for API errors
        const message = err.response?.data?.message || err.response?.data?.detail || err.message || '의안 목록을 불러오는데 실패했습니다.';
        setError(message);
        console.error('Error fetching bills:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchBills();
  }, [filter]); // Added filter to dependency array

  // Remove filtering based on bill.status as it's not a model field
  // const filteredBills = bills.filter(bill => {
  //   if (filter === 'all') return true;
  //   if (filter === 'in-progress') return bill.status === '진행중';
  //   if (filter === 'completed') return bill.status === '완료';
  //   return true;
  // });
  const filteredBills = bills; // Display all fetched bills for now
  const safeBills = Array.isArray(bills) ? bills : [];
  const filteredBills2 = safeBills.filter(bill => {
    if (filter === 'all') return true;
    return bill.status === filter;
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

          {safeBills.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600">표시할 의안이 없습니다.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {filteredBills2.map(bill => (
                <BillCard
                  key={bill.bill_id}
                  id={bill.bill_id}
                  number={bill.bill_id} // Use bill_id for number
                  title={bill.bill_nm}
                  description={''} // Pass empty string for description, was bill.summary
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