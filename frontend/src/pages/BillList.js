import React, { useState } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import HeroSection from '../components/HeroSection';
import BillList from '../components/BillList';
import RecentChanges from '../components/RecentChanges';
import DataMetrics from '../components/DataMetrics';
import Footer from '../components/Footer';
import api from '../api';
import { ENDPOINTS } from '../apiConfig';

const BillListPage = () => {
  const [currentFilter, setCurrentFilter] = useState('all');

  const handleFilterChange = (filter) => {
    setCurrentFilter(filter);
  };

  return (
    <div className="relative pt-20 bg-white">
      <NavigationHeader />
      <main>
        <HeroSection onFilterChange={handleFilterChange} />
        <BillList filter={currentFilter} />
        <RecentChanges />
        <DataMetrics />
      </main>
      <Footer />
    </div>
  );
};

export default BillListPage;