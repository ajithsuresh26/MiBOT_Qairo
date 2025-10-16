import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from "./components/Home";
import Loginform from "./components/Loginform";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/home" element={<Home />} />
        <Route path="/" element={<Loginform />} />
      </Routes>
    </Router>
  );
}

export default App;
