import "@/App.css";
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { initAnalytics, trackPageView } from "@/lib/analytics";

import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import InstallPrompt from "@/components/InstallPrompt";
import SupportChat from "@/components/SupportChat";
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
import OrganizerTransfers from "@/pages/OrganizerTransfers";
import CheckIn from "@/pages/CheckIn";
import Admin from "@/pages/Admin";
import AdminRevenue from "@/pages/AdminRevenue";
import AuthCallback from "@/pages/AuthCallback";
import BecomeOrganizer from "@/pages/BecomeOrganizer";
import BecomePartner from "@/pages/BecomePartner";
import About from "@/pages/About";
import Contact from "@/pages/Contact";
import OrganizerProfile from "@/pages/OrganizerProfile";
import TransferClaim from "@/pages/TransferClaim";
import ScannerEntry from "@/pages/ScannerEntry";
import InfluencerHub from "@/pages/InfluencerHub";
import InfluencerOnboarding from "@/pages/InfluencerOnboarding";
import InfluencerCampaigns from "@/pages/InfluencerCampaigns";
import InfluencerPayouts from "@/pages/InfluencerPayouts";
import InfluencerMarketplace from "@/pages/InfluencerMarketplace";
import InfluencerProfile from "@/pages/InfluencerProfile";
import Flyer from "@/pages/Flyer";
import Features from "@/pages/Features";
import Terms from "@/pages/Terms";
import Feedback from "@/pages/Feedback";
import GiftCards from "@/pages/GiftCards";
import GiftCardSuccess from "@/pages/GiftCardSuccess";
import BundleDetail from "@/pages/BundleDetail";
import BundleSuccess from "@/pages/BundleSuccess";
import BundleManager from "@/pages/BundleManager";
import OrganizerReferral from "@/pages/OrganizerReferral";
import OrganizerBuyers from "@/pages/OrganizerBuyers";
import VsEventbrite from "@/pages/VsEventbrite";
import EventShare from "@/pages/EventShare";
import Blog from "@/pages/Blog";
import BlogPost from "@/pages/BlogPost";
import BlogUnsubscribe from "@/pages/BlogUnsubscribe";
import PartnerPortal from "@/pages/PartnerPortal";
import Help from "@/pages/Help";
import Privacy from "@/pages/Privacy";
import RequireOrganizer from "@/components/RequireOrganizer";

function AppRouter() {
  const location = useLocation();

  // Fire a GA4 page_view event on every SPA route change. React Router doesn't
  // trigger real browser navigations, so we need to do this manually otherwise
  // Google sees only the initial landing.
  useEffect(() => {
    trackPageView(location.pathname + location.search);
  }, [location.pathname, location.search]);

  // Handle OAuth callback session_id in URL fragment BEFORE any other route logic
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  // Scanner PWA — render WITHOUT the main Layout (no nav, no footer, no
  // banners). Scoped to /scan/* so install prompt has the right scope.
  if (location.pathname.startsWith("/scan")) {
    return (
      <Routes>
        <Route path="/scan" element={<ScannerEntry />} />
        <Route path="/scan/:eventId" element={<CheckIn />} />
      </Routes>
    );
  }
  // Marketing flyer — chrome-less so Ctrl+P produces a clean A4 PDF.
  if (location.pathname === "/flyer") {
    return (
      <Routes>
        <Route path="/flyer" element={<Flyer />} />
      </Routes>
    );
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
        <Route path="/become-partner" element={<BecomePartner />} />
        <Route path="/about" element={<About />} />
        <Route path="/vs-eventbrite" element={<VsEventbrite />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/organizers/:id" element={<OrganizerProfile />} />
        <Route path="/transfer/:id" element={<TransferClaim />} />
        <Route path="/influencers" element={<InfluencerMarketplace />} />
        <Route path="/influencers/:id" element={<InfluencerProfile />} />
        <Route path="/influencer" element={<InfluencerHub />} />
        <Route path="/influencer/onboarding" element={<InfluencerOnboarding />} />
        <Route path="/influencer/campaigns" element={<InfluencerCampaigns />} />
        <Route path="/influencer/payouts" element={<InfluencerPayouts />} />
        <Route path="/flyer" element={<Flyer />} />
        <Route path="/features" element={<Features />} />
        <Route path="/feedback/:id" element={<Feedback />} />
        <Route path="/gift-cards" element={<GiftCards />} />
        <Route path="/gift-cards/success" element={<GiftCardSuccess />} />
        <Route path="/bundles/:bundleId" element={<BundleDetail />} />
        <Route path="/bundles/:bundleId/success" element={<BundleSuccess />} />
        <Route path="/events/:id/share" element={<EventShare />} />
        <Route path="/blog" element={<Blog />} />
        <Route path="/blog/unsubscribe" element={<BlogUnsubscribe />} />
        <Route path="/blog/:slug" element={<BlogPost />} />
        <Route path="/partner" element={<PartnerPortal />} />
        <Route path="/help" element={<Help />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/organizer" element={<RequireOrganizer><Organizer /></RequireOrganizer>} />
        <Route path="/organizer/new" element={<RequireOrganizer><CreateEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId/edit" element={<RequireOrganizer><CreateEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId" element={<RequireOrganizer><OrganizerEvent /></RequireOrganizer>} />
        <Route path="/organizer/events/:eventId/checkin" element={<RequireOrganizer><CheckIn /></RequireOrganizer>} />
        <Route path="/organizer/codes" element={<RequireOrganizer><DiscountCodes /></RequireOrganizer>} />
        <Route path="/organizer/payouts" element={<RequireOrganizer><OrganizerPayouts /></RequireOrganizer>} />
        <Route path="/organizer/transfers" element={<RequireOrganizer><OrganizerTransfers /></RequireOrganizer>} />
        <Route path="/organizer/bundles" element={<RequireOrganizer><BundleManager /></RequireOrganizer>} />
        <Route path="/organizer/referral" element={<RequireOrganizer><OrganizerReferral /></RequireOrganizer>} />
        <Route path="/organizer/buyers" element={<RequireOrganizer><OrganizerBuyers /></RequireOrganizer>} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/admin/revenue" element={<AdminRevenue />} />
      </Routes>
    </Layout>
  );
}

function App() {
  // One-time gtag.js injection. No-ops when REACT_APP_GA_MEASUREMENT_ID is unset.
  useEffect(() => { initAnalytics(); }, []);

  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <ErrorBoundary>
            <AppRouter />
          </ErrorBoundary>
          <InstallPrompt />
          <SupportChat />
          <Toaster theme="dark" position="bottom-right" toastOptions={{ style: { background: "#17171b", border: "1px solid #26262c", color: "#f5f5f4" } }} />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
