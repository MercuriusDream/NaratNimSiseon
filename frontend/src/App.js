import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import SessionList from './pages/SessionList';
import SessionDetail from './pages/SessionDetail';
import BillList from './pages/BillList';
import BillDetail from './pages/BillDetail';
import SpeakerList from './pages/SpeakerList';
import SpeakerDetail from './pages/SpeakerDetail';
import PartyList from './pages/PartyList';
import PartyDetail from './pages/PartyDetail';
import Home from './pages/Home';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/sessions" element={<SessionList />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/bills" element={<BillList />} />
          <Route path="/bills/:id" element={<BillDetail />} />
          <Route path="/speakers" element={<SpeakerList />} />
          <Route path="/speakers/:id" element={<SpeakerDetail />} />
          <Route path="/parties" element={<PartyList />} />
          <Route path="/parties/:id" element={<PartyDetail />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
