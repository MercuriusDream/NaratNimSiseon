import React, { useState, useEffect } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import SentimentDashboard from '../components/SentimentDashboard';

function SentimentAnalysis() {
  const [activeTab, setActiveTab] = useState('overall');
  const [parties, setParties] = useState([]);
  const [selectedParty, setSelectedParty] = useState(null);

  useEffect(() => {
    fetchParties();
  }, []);

  const fetchParties = async () => {
    try {
      const response = await fetch('/api/parties/');
      const data = await response.json();
      if (data.results) {
        setParties(data.results);
      }
    } catch (error) {
      console.error('Error fetching parties:', error);
    }
  };

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <div className="container mx-auto px-4 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">감성 분석 대시보드</h1>
            <p className="text-lg text-gray-600">
              국회 발언과 투표 기록을 바탕으로 한 종합적인 감성 분석 결과를 확인하세요.
            </p>
          </div>

          {/* Tab Navigation */}
          <div className="bg-white rounded-lg shadow mb-6">
            <div className="border-b border-gray-200">
              <nav className="-mb-px flex space-x-8 px-6">
                <button
                  onClick={() => setActiveTab('overall')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'overall'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  전체 분석
                </button>
                <button
                  onClick={() => setActiveTab('category')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'category'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  카테고리별 분석
                </button>
                <button
                  onClick={() => setActiveTab('party')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'party'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  정당별 분석
                </button>
              </nav>
            </div>
          </div>

          {/* Tab Content */}
          {activeTab === 'overall' && (
            <SentimentDashboard />
          )}

          {activeTab === 'category' && (
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-2xl font-bold mb-4">정책 카테고리별 감성 분석</h2>
                <p className="text-gray-600 mb-6">
                  주요 정책 분야별로 국회의원들의 발언 감성을 분석합니다.
                  각 카테고리의 하위 분야와 정당별 입장 차이를 확인할 수 있습니다.
                </p>
              </div>
              <SentimentDashboard />
            </div>
          )}

          {activeTab === 'party' && (
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-2xl font-bold mb-4">정당별 감성 분석</h2>
                <p className="text-gray-600 mb-6">
                  특정 정당의 감성 분석 결과를 확인하세요. 
                  발언과 투표 기록을 종합하여 정당의 정책 성향을 분석합니다.
                </p>

                <div className="mb-6">
                  <label htmlFor="party-select" className="block text-sm font-medium text-gray-700 mb-2">
                    분석할 정당 선택:
                  </label>
                  <select
                    id="party-select"
                    value={selectedParty || ''}
                    onChange={(e) => setSelectedParty(e.target.value || null)}
                    className="border border-gray-300 rounded-md px-3 py-2 bg-white"
                  >
                    <option value="">정당을 선택하세요</option>
                    {parties.map((party) => (
                      <option key={party.id} value={party.id}>
                        {party.name} ({party.assembly_era}대)
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {selectedParty && (
                <SentimentDashboard partyId={selectedParty} />
              )}
            </div>
          )}

          {/* Information Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-8">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
              <div className="flex items-center mb-3">
                <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                  💬
                </div>
                <h3 className="text-lg font-semibold text-blue-900 ml-3">발언 감성 분석</h3>
              </div>
              <p className="text-blue-800 text-sm">
                국회 회의록에서 추출한 발언 내용을 AI로 분석하여 감성 점수를 산출합니다.
              </p>
            </div>

            <div className="bg-green-50 border border-green-200 rounded-lg p-6">
              <div className="flex items-center mb-3">
                <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                  🗳️
                </div>
                <h3 className="text-lg font-semibold text-green-900 ml-3">투표 기록 분석</h3>
              </div>
              <p className="text-green-800 text-sm">
                의안에 대한 찬성/반대 투표 기록을 바탕으로 정량적 감성 점수를 제공합니다.
              </p>
            </div>

            <div className="bg-purple-50 border border-purple-200 rounded-lg p-6">
              <div className="flex items-center mb-3">
                <div className="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                  📊
                </div>
                <h3 className="text-lg font-semibold text-purple-900 ml-3">종합 분석</h3>
              </div>
              <p className="text-purple-800 text-sm">
                발언과 투표를 종합하여 각 의원과 정당의 정책별 입장을 분석합니다.
              </p>
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default SentimentAnalysis;