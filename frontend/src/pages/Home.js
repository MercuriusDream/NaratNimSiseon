
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
        const baseURL = window.location.origin;
        const [partyRes, meetingRes, billRes] = await Promise.all([
          fetch(`${baseURL}/api/parties/?page_size=4`),
          fetch(`${baseURL}/api/sessions/?page_size=3`),
          fetch(`${baseURL}/api/bills/?page_size=3`),
        ]);

        if (!partyRes.ok || !meetingRes.ok || !billRes.ok) {
          throw new Error('Failed to fetch data');
        }

        const partyData = await partyRes.json();
        const meetingData = await meetingRes.json();
        const billData = await billRes.json();
        
        setParties(partyData.results || []);
        setMeetings(meetingData.results || []);
        setBills(billData.results || []);
      } catch (err) {
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        console.error('Error fetching home data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex overflow-hidden flex-col bg-white">
        <NavigationHeader />
        <main className="flex flex-col self-center w-full max-w-[1440px] max-md:max-w-full">
          <div className="flex items-center justify-center h-96">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex overflow-hidden flex-col bg-white">
        <NavigationHeader />
        <main className="flex flex-col self-center w-full max-w-[1440px] max-md:max-w-full">
          <div className="flex items-center justify-center h-96">
            <div className="text-red-600 text-center">{error}</div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white">
      <NavigationHeader />
      <main className="flex flex-col self-center w-full max-w-[1440px] max-md:max-w-full">
        <HeroSection />
        
        {/* 주요 정당 소개 섹션 */}
        <ContentSection
          title="주요 정당 소개"
          description="시민들이 알아야 할 정당들입니다."
          buttonText="모든 정당 보기"
          buttonLink="/parties"
        >
          <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
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
          <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
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
          <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
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
