import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

const BillList = ({ filter }) => {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({});
  const [currentPage, setCurrentPage] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    fetchBills();
  }, [filter, currentPage]);

  const fetchBills = async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      if (filter && filter !== 'all') {
        params.append('status', filter);
      }
      params.append('page', currentPage);

      const response = await api.get(`/api/bills/?${params}`).catch(() => ({
        data: { results: [], count: 0, next: null, previous: null }
      }));

      // Handle different response structures
      const billsData = response.data?.results || response.data || [];
      const paginationData = {
        count: response.data?.count || billsData.length,
        next: response.data?.next,
        previous: response.data?.previous
      };

      setBills(Array.isArray(billsData) ? billsData : []);
      setPagination(paginationData);
    } catch (err) {
      setError('의안 목록을 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching bills:', err);
      setBills([]);
      setPagination({ count: 0, next: null, previous: null });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Bill list rendering logic */}
      {loading && <p>Loading bills...</p>}
      {error && <p>Error: {error}</p>}
      {bills && bills.map(bill => (
        <div key={bill.id} className="border p-4 mb-4 rounded-lg cursor-pointer hover:shadow-md" onClick={() => navigate(`/bills/${bill.bill_id}`)}>
          <h3 className="font-semibold text-lg mb-2">{bill.bill_nm}</h3>
          <p className="text-gray-600 mb-2">의안번호: {bill.bill_id}</p>
          {bill.summary && <p className="text-gray-700">{bill.summary}</p>}
        </div>
      ))}

      {/* Pagination */}
      {pagination.count > 10 && (
        <div className="flex justify-center space-x-2 mt-8">
          <button
            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
            disabled={!pagination.previous}
            className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            이전
          </button>
          <span className="px-4 py-2 text-gray-700">
            페이지 {currentPage} / {Math.ceil(pagination.count / 10)}
          </span>
          <button
            onClick={() => setCurrentPage(prev => prev + 1)}
            disabled={!pagination.next}
            className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
};

export default BillList;