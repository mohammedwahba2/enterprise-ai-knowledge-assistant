# Final refined mockup — The Reading Room

Throwaway HTML (not product code). Synthetic content only.

```bash
cd docs/design/final && python3 -m http.server 8766
# open http://localhost:8766/
```

Use the dark bar at the bottom: screens (Home, Chat + evidence, Not found, Library, Viewer), EN/عربي, Desktop/Tablet/Mobile frames, ⌘K palette, evidence drawer toggle. ⌘K / Esc also work on the keyboard.
URL params for screenshots: `?screen=chat&lang=ar&device=mobile&cite=2&sheet=1&palette=1`.
Click a citation marker or margin note in Chat to move the evidence pane to that passage.
Layouts use CSS container queries on the frame, so the Tablet/Mobile frames behave like real viewports.
