import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";

import Layout from "@/components/Layout";
import Landing from "@/pages/Landing";
import Events from "@/pages/Events";
import EventDetail from "@/pages/EventDetail";
import Checkout from "@/pages/Checkout";
import CheckoutSuccess from "@/pages/CheckoutSuccess";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Profile from "@/pages/Profile";
import Organizer from "@/pages/Organizer";
import OrganizerEvent from "@/pages/OrganizerEvent";
import CreateEvent from "@/pages/CreateEvent";
import DiscountCodes from "@/pages/DiscountCodes";
import CheckIn from "@/pages/CheckIn";
import Admin from "@/pages/Admin";
import AuthCallback from "@/pages/AuthCallback";

function AppRouter() {
  const location = useLocation();
  // Handle OAuth callback session_id in URL fragment BEFORE any other route logic
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/events" element={<Events />} />
        <Route path="/events/:eventId" element={<EventDetail />} />
        <Route path="/checkout/:bookingId" element={<Checkout />} />
        <Route path="/checkout/success" element={<CheckoutSuccess />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/organizer" element={<Organizer />} />
        <Route path="/organizer/new" element={<CreateEvent />} />
        <Route path="/organizer/events/:eventId" element={<OrganizerEvent />} />
        <Route path="/organizer/events/:eventId/checkin" element={<CheckIn />} />
        <Route path="/organizer/codes" element={<DiscountCodes />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster theme="dark" position="bottom-right" toastOptions={{ style: { background: "#17171b", border: "1px solid #26262c", color: "#f5f5f4" } }} />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
