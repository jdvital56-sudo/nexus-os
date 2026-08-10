# NEXUS OS Frontend

React + TypeScript + Vite frontend for Claude Code OS dashboard.

## Features

- **Dashboard**: ROI tracking, API usage monitoring, system status
- **Knowledge Graph**: Interactive 3D graph visualization with ForceGraph2D
- **Memory Management**: Visual representation of memory nodes and connections
- **Skills Framework**: Track and manage AI skills performance
- **Dream Review**: View nightly analysis reports
- **Agents Panel**: Monitor and control AI agents

## Tech Stack

- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Recharts (analytics)
- React Force Graph 2D (knowledge graph)
- Lucide React (icons)
- Axios (API client)

## Getting Started

### Install dependencies

```bash
npm install
```

### Configure environment

Create `.env` file:

```bash
VITE_API_URL=http://localhost:8000/api
```

### Run development server

```bash
npm run dev
```

### Build for production

```bash
npm run build
```

## Project Structure

```
src/
├── components/     # Reusable UI components
│   └── Sidebar.tsx
├── screens/        # Page components
│   ├── HomeScreen.tsx      # Dashboard
│   ├── GraphScreen.tsx     # Knowledge Graph
│   └── ...
├── hooks/          # Custom React hooks
│   └── useApi.ts
├── lib/            # Utilities and API clients
│   └── api.ts
├── types/          # TypeScript interfaces
│   └── index.ts
├── App.tsx         # Main app component
├── main.tsx        # Entry point
└── index.css       # Global styles
```

## API Integration

The frontend connects to the backend API at `/api`. See `src/lib/api.ts` for available endpoints:

- Analytics: Overview, API Usage, ROI
- Dream Review: Latest report, history, trigger
- Skills: CRUD operations, auto-generate
- Memory: Graph data, search, nodes
- Agents: List, status, control
- System: Status, setup wizard, connections

## Mock Data

Currently using mock data for demonstration. To connect to real backend:

1. Uncomment API calls in screen components
2. Ensure backend is running on port 8000
3. Set correct `VITE_API_URL` in `.env`
