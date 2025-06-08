const fetchSentimentData = async () => {
    try {
      setLoading(true);
      setError(null);

      if (billId) {
        const response = await api.get(`/api/bills/${billId}/voting-sentiment/`);
        setSentimentData(response.data);
      } else {
        const response = await api.get(`/api/analytics/overall-sentiment/?time_range=${timeRange}`);
        setSentimentData(response.data);
      }
    } catch (err) {
      console.error('Error fetching sentiment data:', err);
      setError('감성 분석 데이터를 불러오는 중 오류가 발생했습니다.');
      setSentimentData(null); // Ensure we reset data on error
    } finally {
      setLoading(false);
    }
  };