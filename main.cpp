// Find & Reward -- C++ CLI simulation
// ------------------------------------
// An OOP terminal simulation of the crowdsourced geo-bounty platform:
// post a lost item/pet bounty, broadcast it to nearby simulated users
// within a paid radius (Haversine distance), accept "found it" claims,
// and release a split reward from a simple in-memory escrow ledger.
//
// Build:  g++ -std=c++17 -O2 -o geobounty main.cpp
// Run:    ./geobounty

#include <iostream>
#include <iomanip>
#include <vector>
#include <string>
#include <cmath>
#include <random>
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <optional>
#include <sstream>

// ----------------------------------------------------------------- geo ----

constexpr double EARTH_RADIUS_KM = 6371.0;

struct GeoPoint {
    double lat;
    double lon;
};

double toRadians(double deg) { return deg * M_PI / 180.0; }

double haversineKm(const GeoPoint& a, const GeoPoint& b) {
    double dLat = toRadians(b.lat - a.lat);
    double dLon = toRadians(b.lon - a.lon);
    double lat1 = toRadians(a.lat);
    double lat2 = toRadians(b.lat);

    double h = std::sin(dLat / 2) * std::sin(dLat / 2) +
               std::cos(lat1) * std::cos(lat2) *
               std::sin(dLon / 2) * std::sin(dLon / 2);
    double c = 2 * std::atan2(std::sqrt(h), std::sqrt(1 - h));
    return EARTH_RADIUS_KM * c;
}

std::pair<double, double> splitReward(double total, int finderPct) {
    finderPct = std::max(0, std::min(100, finderPct));
    double finderShare = std::round(total * finderPct / 100.0 * 100.0) / 100.0;
    double platformShare = std::round((total - finderShare) * 100.0) / 100.0;
    return {finderShare, platformShare};
}

// --------------------------------------------------------------- models ---

struct User {
    int id;
    std::string name;
    GeoPoint location;
    int reputation = 0;
};

enum class BountyStatus { Active, Resolved, Cancelled };
enum class ClaimStatus { Pending, Approved, Rejected };

std::string statusToStr(BountyStatus s) {
    switch (s) {
        case BountyStatus::Active: return "active";
        case BountyStatus::Resolved: return "resolved";
        case BountyStatus::Cancelled: return "cancelled";
    }
    return "?";
}

std::string statusToStr(ClaimStatus s) {
    switch (s) {
        case ClaimStatus::Pending: return "pending";
        case ClaimStatus::Approved: return "approved";
        case ClaimStatus::Rejected: return "rejected";
    }
    return "?";
}

struct Bounty {
    int id;
    std::string posterName;
    std::string category;   // "item" or "pet"
    std::string itemName;
    std::string description;
    GeoPoint location;
    double radiusKm;
    double rewardTotal;
    int finderPct;
    BountyStatus status = BountyStatus::Active;
};

struct Claim {
    int id;
    int bountyId;
    std::string finderName;
    std::string proofNote;
    ClaimStatus status = ClaimStatus::Pending;
};

struct LedgerEntry {
    int id;
    int bountyId;
    int claimId;
    std::string finderName;
    double finderShare;
    double platformShare;
};

// A user within a bounty's radius, with the computed distance attached.
struct BroadcastTarget {
    User user;
    double distanceKm;
};

// ------------------------------------------------------------- platform ---

class GeoBountyPlatform {
public:
    void seedDemoUsers(const GeoPoint& center, int count, double spreadKm) {
        std::mt19937 rng(42);  // fixed seed -> reproducible demo run
        std::uniform_real_distribution<double> unit(0.0, 1.0);
        static const std::vector<std::string> names = {
            "Aisha", "Rohan", "Priya", "Kabir", "Meera", "Arjun", "Sana", "Dev",
            "Neha", "Vikram", "Isha", "Farhan", "Tanvi", "Aman", "Riya", "Yusuf",
        };
        for (int i = 0; i < count; ++i) {
            double r = spreadKm * std::sqrt(unit(rng));
            double theta = unit(rng) * 2 * M_PI;
            double dLat = (r / EARTH_RADIUS_KM) * (180.0 / M_PI);
            double dLon = (r / EARTH_RADIUS_KM) * (180.0 / M_PI) / std::cos(toRadians(center.lat));
            GeoPoint p{center.lat + dLat * std::cos(theta), center.lon + dLon * std::sin(theta)};
            users_.push_back(User{nextUserId_++, names[i % names.size()], p, 0});
        }
    }

    const std::vector<User>& users() const { return users_; }

    int postBounty(const std::string& poster, const std::string& category,
                    const std::string& itemName, const std::string& description,
                    GeoPoint loc, double radiusKm, double reward, int finderPct) {
        Bounty b{nextBountyId_++, poster, category, itemName, description,
                 loc, radiusKm, reward, finderPct, BountyStatus::Active};
        bounties_.push_back(b);
        return b.id;
    }

    std::vector<Bounty> activeBounties() const {
        std::vector<Bounty> out;
        for (const auto& b : bounties_)
            if (b.status == BountyStatus::Active) out.push_back(b);
        return out;
    }

    std::optional<Bounty> findBounty(int id) const {
        for (const auto& b : bounties_) if (b.id == id) return b;
        return std::nullopt;
    }

    std::vector<BroadcastTarget> broadcastTargets(int bountyId) const {
        std::vector<BroadcastTarget> targets;
        auto bountyOpt = findBounty(bountyId);
        if (!bountyOpt) return targets;
        const Bounty& b = *bountyOpt;
        for (const auto& u : users_) {
            double d = haversineKm(b.location, u.location);
            if (d <= b.radiusKm) targets.push_back({u, d});
        }
        std::sort(targets.begin(), targets.end(),
                  [](const BroadcastTarget& a, const BroadcastTarget& b) { return a.distanceKm < b.distanceKm; });
        return targets;
    }

    int submitClaim(int bountyId, const std::string& finderName, const std::string& proofNote) {
        Claim c{nextClaimId_++, bountyId, finderName, proofNote, ClaimStatus::Pending};
        claims_.push_back(c);
        return c.id;
    }

    std::vector<Claim> pendingClaims(int bountyId) const {
        std::vector<Claim> out;
        for (const auto& c : claims_)
            if (c.bountyId == bountyId && c.status == ClaimStatus::Pending) out.push_back(c);
        return out;
    }

    LedgerEntry approveClaim(int claimId) {
        Claim* claim = nullptr;
        for (auto& c : claims_) if (c.id == claimId) { claim = &c; break; }
        if (!claim) throw std::runtime_error("Claim not found");

        Bounty* bounty = nullptr;
        for (auto& b : bounties_) if (b.id == claim->bountyId) { bounty = &b; break; }
        if (!bounty) throw std::runtime_error("Bounty not found");
        if (bounty->status != BountyStatus::Active) throw std::runtime_error("Bounty is no longer active");

        auto [finderShare, platformShare] = splitReward(bounty->rewardTotal, bounty->finderPct);

        claim->status = ClaimStatus::Approved;
        for (auto& c : claims_)
            if (c.bountyId == bounty->id && c.id != claimId && c.status == ClaimStatus::Pending)
                c.status = ClaimStatus::Rejected;
        bounty->status = BountyStatus::Resolved;

        for (auto& u : users_) if (u.name == claim->finderName) u.reputation += 1;

        LedgerEntry entry{nextLedgerId_++, bounty->id, claim->id, claim->finderName, finderShare, platformShare};
        ledger_.push_back(entry);
        return entry;
    }

    void rejectClaim(int claimId) {
        for (auto& c : claims_) if (c.id == claimId) { c.status = ClaimStatus::Rejected; return; }
        throw std::runtime_error("Claim not found");
    }

    void cancelBounty(int bountyId) {
        for (auto& b : bounties_) if (b.id == bountyId) { b.status = BountyStatus::Cancelled; return; }
        throw std::runtime_error("Bounty not found");
    }

    const std::vector<LedgerEntry>& ledger() const { return ledger_; }
    const std::vector<Claim>& allClaims() const { return claims_; }

private:
    std::vector<User> users_;
    std::vector<Bounty> bounties_;
    std::vector<Claim> claims_;
    std::vector<LedgerEntry> ledger_;
    int nextUserId_ = 1;
    int nextBountyId_ = 1;
    int nextClaimId_ = 1;
    int nextLedgerId_ = 1;
};

// -------------------------------------------------------------- CLI I/O ---

std::string money(double v) {
    std::ostringstream oss;
    oss << "Rs " << std::fixed << std::setprecision(2) << v;
    return oss.str();
}

int readInt(const std::string& prompt) {
    while (true) {
        std::cout << prompt;
        std::string line;
        std::getline(std::cin, line);
        try {
            return std::stoi(line);
        } catch (...) {
            std::cout << "  Please enter a whole number.\n";
        }
    }
}

double readDouble(const std::string& prompt) {
    while (true) {
        std::cout << prompt;
        std::string line;
        std::getline(std::cin, line);
        try {
            return std::stod(line);
        } catch (...) {
            std::cout << "  Please enter a number.\n";
        }
    }
}

std::string readLine(const std::string& prompt) {
    std::cout << prompt;
    std::string line;
    std::getline(std::cin, line);
    return line;
}

void printBounty(const Bounty& b) {
    std::cout << "  #" << b.id << " [" << statusToStr(b.status) << "] "
              << b.itemName << " (" << b.category << ") -- " << money(b.rewardTotal)
              << ", radius " << b.radiusKm << " km, finder " << b.finderPct << "%\n"
              << "      posted by " << b.posterName << " at ("
              << std::fixed << std::setprecision(5) << b.location.lat << ", " << b.location.lon << ")\n";
    if (!b.description.empty()) std::cout << "      \"" << b.description << "\"\n";
}

void listActiveBounties(const GeoBountyPlatform& platform) {
    auto active = platform.activeBounties();
    if (active.empty()) { std::cout << "  (no active bounties)\n"; return; }
    for (const auto& b : active) printBounty(b);
}

void postBountyFlow(GeoBountyPlatform& platform, const GeoPoint& cityCenter) {
    std::cout << "\n-- Post a bounty --\n";
    std::string poster = readLine("Your name: ");
    std::string category = readLine("Category (item/pet): ");
    std::string itemName = readLine("What was lost? ");
    std::string description = readLine("Description: ");
    double latOffsetKm = readDouble("How far from city center is the last-known spot? (km, 0-10): ");
    double bearingDeg = readDouble("Direction from center, degrees (0=N, 90=E): ");
    double radiusKm = readDouble("Paid broadcast radius (km): ");
    double reward = readDouble("Total reward (Rs): ");
    int finderPct = readInt("Finder's share of reward (0-100): ");

    double theta = toRadians(bearingDeg);
    double dLat = (latOffsetKm / EARTH_RADIUS_KM) * (180.0 / M_PI);
    double dLon = (latOffsetKm / EARTH_RADIUS_KM) * (180.0 / M_PI) / std::cos(toRadians(cityCenter.lat));
    GeoPoint loc{cityCenter.lat + dLat * std::cos(theta), cityCenter.lon + dLon * std::sin(theta)};

    int id = platform.postBounty(poster, category, itemName, description, loc, radiusKm, reward, finderPct);
    auto [finderShare, platformShare] = splitReward(reward, finderPct);
    std::cout << "Posted bounty #" << id << ". Escrow funded with " << money(reward)
              << " (finder " << money(finderShare) << " / platform " << money(platformShare) << " on release).\n";
}

void broadcastFlow(const GeoBountyPlatform& platform) {
    std::cout << "\n-- Broadcast simulation --\n";
    listActiveBounties(platform);
    int id = readInt("Bounty # to broadcast: ");
    auto targets = platform.broadcastTargets(id);
    if (targets.empty()) {
        std::cout << "  No demo users currently fall inside this bounty's radius.\n";
        return;
    }
    std::cout << "  " << targets.size() << " user(s) notified:\n";
    for (const auto& t : targets) {
        std::cout << "    " << t.user.name << " -- " << std::fixed << std::setprecision(2)
                  << t.distanceKm << " km away\n";
    }
}

void claimFlow(GeoBountyPlatform& platform) {
    std::cout << "\n-- Submit a claim --\n";
    listActiveBounties(platform);
    int id = readInt("Bounty # you found: ");
    std::string finder = readLine("Finder's name: ");
    std::string note = readLine("Proof note (stand-in for a geotagged photo): ");
    platform.submitClaim(id, finder, note);
    std::cout << "Claim submitted, pending owner verification.\n";
}

void resolveFlow(GeoBountyPlatform& platform) {
    std::cout << "\n-- Resolve pending claims --\n";
    listActiveBounties(platform);
    int id = readInt("Bounty # to review claims for: ");
    auto pending = platform.pendingClaims(id);
    if (pending.empty()) { std::cout << "  No pending claims for that bounty.\n"; return; }
    for (const auto& c : pending)
        std::cout << "  claim #" << c.id << " by " << c.finderName << " -- \"" << c.proofNote << "\"\n";
    int claimId = readInt("Claim # to approve (0 to skip): ");
    if (claimId == 0) return;
    std::string decision = readLine("Approve or reject? (a/r): ");
    try {
        if (decision == "a" || decision == "A") {
            LedgerEntry entry = platform.approveClaim(claimId);
            std::cout << "Escrow released: " << entry.finderName << " gets " << money(entry.finderShare)
                      << ", platform keeps " << money(entry.platformShare) << ".\n";
        } else {
            platform.rejectClaim(claimId);
            std::cout << "Claim rejected.\n";
        }
    } catch (const std::exception& e) {
        std::cout << "  Error: " << e.what() << "\n";
    }
}

void ledgerFlow(const GeoBountyPlatform& platform) {
    std::cout << "\n-- Escrow ledger --\n";
    const auto& ledger = platform.ledger();
    if (ledger.empty()) { std::cout << "  (no releases yet)\n"; return; }
    double totalFinder = 0, totalPlatform = 0;
    for (const auto& e : ledger) {
        std::cout << "  ledger #" << e.id << " bounty #" << e.bountyId << " -> " << e.finderName
                  << " " << money(e.finderShare) << " | platform " << money(e.platformShare) << "\n";
        totalFinder += e.finderShare;
        totalPlatform += e.platformShare;
    }
    std::cout << "  Totals: finders " << money(totalFinder) << ", platform " << money(totalPlatform) << "\n";
}

void listUsersFlow(const GeoBountyPlatform& platform) {
    std::cout << "\n-- Demo users --\n";
    for (const auto& u : platform.users()) {
        std::cout << "  " << u.id << ". " << u.name << " ("
                  << std::fixed << std::setprecision(5) << u.location.lat << ", " << u.location.lon
                  << ") rep=" << u.reputation << "\n";
    }
}

void printMenu() {
    std::cout << "\n===== Find & Reward -- CLI simulation =====\n"
              << " 1) Post a bounty\n"
              << " 2) List active bounties\n"
              << " 3) Simulate broadcast (who gets notified)\n"
              << " 4) Submit a 'found it' claim\n"
              << " 5) Resolve pending claims (approve/reject)\n"
              << " 6) View escrow ledger\n"
              << " 7) List demo users\n"
              << " 0) Exit\n"
              << "Choose: ";
}

int main() {
    GeoBountyPlatform platform;
    const GeoPoint cityCenter{19.0760, 72.8777};  // Mumbai
    platform.seedDemoUsers(cityCenter, 16, 6.0);

    std::cout << "Find & Reward CLI simulation -- seeded " << platform.users().size()
              << " demo users around Mumbai (19.0760, 72.8777).\n";

    while (true) {
        printMenu();
        std::string line;
        std::getline(std::cin, line);
        if (line.empty()) continue;
        int choice;
        try { choice = std::stoi(line); } catch (...) { std::cout << "  Please enter a number.\n"; continue; }

        if (choice == 0) { std::cout << "Goodbye.\n"; break; }
        switch (choice) {
            case 1: postBountyFlow(platform, cityCenter); break;
            case 2: std::cout << "\n-- Active bounties --\n"; listActiveBounties(platform); break;
            case 3: broadcastFlow(platform); break;
            case 4: claimFlow(platform); break;
            case 5: resolveFlow(platform); break;
            case 6: ledgerFlow(platform); break;
            case 7: listUsersFlow(platform); break;
            default: std::cout << "  Unknown option.\n";
        }
    }
    return 0;
}
