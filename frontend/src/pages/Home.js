
import React, { useEffect, useState } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import HeroSection from '../components/HeroSection';
import ContentSection from '../components/ContentSection';
import Footer from '../components/Footer';
import PartyCard from '../components/PartyCard';
import MeetingCard from '../components/MeetingCard';
import BillCard from '../components/BillCard';

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
        
        // Use relative URLs for API calls
        const [partyRes, meetingRes, billRes] = await Promise.all([
          fetch('/api/parties/?page_size=4'),
          fetch('/api/sessions/?page_size=3'),
          fetch('/api/bills/?page_size=3'),
        ]);

        // Check if responses are ok
        if (partyRes.ok && meetingRes.ok && billRes.ok) {
          const partyData = await partyRes.json();
          const meetingData = await meetingRes.json();
          const billData = await billRes.json();
          
          setParties(partyData.results || []);
          setMeetings(meetingData.results || []);
          setBills(billData.results || []);
        } else {
          // If API calls fail, set empty arrays to at least show the UI
          setParties([]);
          setMeetings([]);
          setBills([]);
          console.warn('Some API calls failed, showing empty data');
        }
      } catch (err) {
        // On error, show the UI with empty data rather than error state
        setParties([]);
        setMeetings([]);
        setBills([]);
        console.error('Error fetching home data:', err);
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
                key={meeting.id}
                id={meeting.id}
                title={meeting.title || meeting.conf_nm}
                date={meeting.conf_dt}
                description={meeting.summary || ''}
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
                id={bill.bill_id}
                title={bill.bill_nm}
                date={bill.created_at}
                description={bill.summary || ''}
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
