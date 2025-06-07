import React, { useEffect, useState } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import HeroSection from '../components/HeroSection';
import ContentSection from '../components/ContentSection';
import Footer from '../components/Footer';
import PartyCard from '../components/PartyCard';
import MeetingCard from '../components/MeetingCard';
import BillCard from '../components/BillCard';
import api from '../api'; // Import the axios instance
import { ENDPOINTS } from '../apiConfig'; // Import endpoint paths

const Home = () => {
  const [parties, setParties] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null); // Clear previous errors

        const [partyRes, meetingRes, billRes] = await Promise.all([
          api.get(ENDPOINTS.PARTIES, { params: { page_size: 4 } }),
          api.get(ENDPOINTS.SESSIONS, { params: { page_size: 3 } }),
          api.get(ENDPOINTS.BILLS, { params: { page_size: 3 } }),
        ]);

        // Axios responses are in `response.data`
        // DRF paginated responses have results in `response.data.results`
        setParties(partyRes.data.results || partyRes.data || []);
        setMeetings(meetingRes.data.results || meetingRes.data || []);
        setBills(billRes.data.results || billRes.data || []);

        // Note: Promise.all will fail if any request fails.
        // The .ok check is not directly applicable here as Axios throws for non-2xx.
        // The individual error state for partial data load is lost with Promise.all.
        // If partial load is critical, separate try/catch for each api.get would be needed.

      } catch (err) {
        // Axios errors have a `response` object for API errors
        const message = err.response?.data?.message || err.response?.data?.detail || err.message || '데이터를 불러오는 중 오류가 발생했습니다.';
        setError(message);
        console.error('Error fetching home data:', err);
        // Set to empty arrays on error to prevent rendering issues
        setParties([]);
        setMeetings([]);
        setBills([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex overflow-hidden flex-col bg-white min-h-screen">
        <NavigationHeader />
        <main className="flex flex-col w-full">
          <div className="flex items-center justify-center h-96 bg-gradient-to-b from-blue-50 to-white">
            <div className="flex flex-col items-center gap-4">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600"></div>
              <p className="text-slate-600 font-medium">데이터를 불러오는 중...</p>
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex overflow-hidden flex-col bg-white min-h-screen">
        <NavigationHeader />
        <main className="flex flex-col w-full">
          <div className="flex items-center justify-center h-96 bg-gradient-to-b from-red-50 to-white">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 18.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-slate-800 mb-2">오류가 발생했습니다</h3>
              <p className="text-red-600 mb-4">{error}</p>
              <button 
                onClick={() => window.location.reload()} 
                className="px-6 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors duration-200"
              >
                다시 시도
              </button>
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <HeroSection />

        {/* 주요 정당 소개 섹션 */}
        <ContentSection
          title="주요 정당 소개"
          description="시민들이 알아야 할 정당들입니다."
          buttonText="모든 정당 보기"
          buttonLink="/parties"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 w-full">
            {parties.map((party) => (
              <PartyCard
                key={party.id}
                id={party.id}
                image={party.logo_url || '/logo192.png'}
                title={party.name}
                subtitle={party.slogan || ''}
                description={party.description || ''}
              />
            ))}
          </div>
        </ContentSection>

        {/* 최근 회의록 섹션 */}
        <ContentSection
          title="최근 회의록"
          description="정치의 최신 동향을 확인하세요."
          buttonText="모든 회의록 보기"
          buttonLink="/sessions"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 w-full">
            {meetings.map((meeting) => (
              <MeetingCard
                key={meeting.conf_id} // Use conf_id as key
                id={meeting.conf_id}   // Pass conf_id as id
                cmit_nm={meeting.cmit_nm} // Pass cmit_nm
                conf_knd={meeting.conf_knd} // Pass conf_knd
                conf_dt={meeting.conf_dt}   // Pass conf_dt
                // description is removed as per MeetingCard changes
              />
            ))}
          </div>
        </ContentSection>

        {/* 최근 의안 섹션 */}
        <ContentSection
          title="최근 의안"
          description="주요 의안을 확인해보세요."
          buttonText="모든 의안 보기"
          buttonLink="/bills"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 w-full">
            {bills.map((bill) => (
              <BillCard
                key={bill.bill_id}
                id={bill.bill_id} // bill_id for navigation
                title={bill.bill_nm}
                // date prop removed from BillCard
                description={''} // Pass empty string for description
              />
            ))}
          </div>
        </ContentSection>
      </main>
      <Footer />
    </div>
  );
};

export default Home;