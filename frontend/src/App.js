import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";

import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import InstallPrompt from "@/components/InstallPrompt";
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
import OrganizerPayouts from "@/pages/OrganizerPayouts";
import CheckIn from "@/pages/CheckIn";
import Admin from "@/pages/Admin";
import AuthCallback from "@/pages/AuthCallback";
import BecomeOrganizer from "@/pages/BecomeOrganizer";
import About from "@/pages/About";
import Contact from "@/pages/Contact";
import OrganizerProfile from "@/pages/OrganizerProfile";
import RequireOrganizer from "@/components/RequireOrganizer";

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
        <Route path="/become-organizer" element={<BecomeOrganizer />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/organizers/:id" element={<OrganizerProfile />} />
        <Route path="/organizer" element={<RequireOrganizer><Organizer /></RequireOrganizer>} />
        <Route path="/organizer/new" element={<RequireOrganizer><CreateEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId/edit" element={<RequireOrganizer><CreateEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId" element={<RequireOrganizer><OrganizerEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId/checkin" element={<RequireOrganizer><CheckIn /></RequireOrganizer>} />
        {/* Public scanner — no login required, validated by token query param.
            Lets door staff / volunteers scan via a shareable link. */}
        <Route path="/scan/:eventId" element={<CheckIn />} />
        <Route path="/organizer/codes" element={<RequireOrganizer><DiscountCodes /></RequireOrganizer>} />
        <Route path="/organizer/payouts" element={<RequireOrganizer><OrganizerPayouts /></RequireOrganizer>} />
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
          <ErrorBoundary>
            <AppRouter />
          </ErrorBoundary>
          <InstallPrompt />
          <Toaster theme="dark" position="bottom-right" toastOptions={{ style: { background: "#17171b", border: "1px solid #26262c", color: "#f5f5f4" } }} />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
