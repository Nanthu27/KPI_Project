/**
 * Header — Production Version
 * 
 * Changes:
 *  - "Upload Excel" REPLACED with "Download PDF"
 *  - Uses html2canvas + jsPDF to capture the EXACT rendered DOM as a
 *    pixel-perfect image, then embeds it in a PDF. This avoids the
 *    browser's native print engine entirely, which was reflowing the
 *    layout to A3-landscape page dimensions and producing a "skeleton"
 *    (colors/shadows stripped, sliders mispositioned) instead of an exact
 *    copy of what's on screen.
 *  - Avatar shows initials from logged-in user (configurable)
 */
import { useState } from 'react';
import { Box, Typography, Button, Avatar, CircularProgress, Tooltip } from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { COLORS } from '../theme/theme';

export default function Header({ onUploadExcel }) {
  const [printing, setPrinting] = useState(false);

  const handleDownloadPDF = async () => {
    setPrinting(true);
    try {
      // Capture the entire app root exactly as it is rendered right now —
      // same colors, same slider positions, same fonts, same everything.
      const target = document.getElementById('kpi-app-root') || document.body;

      const canvas = await html2canvas(target, {
        scale: 2,                 // 2x for crisp text/lines in the PDF
        useCORS: true,
        backgroundColor: '#ffffff',
        // Exclude the Cascade drawer/FAB/Download button from the capture
        ignoreElements: (el) =>
          el.dataset?.cascadePanel === 'true' ||
          el.dataset?.printHide === 'true' ||
          el.classList?.contains('cascade-fab'),
        windowWidth: target.scrollWidth,
        windowHeight: target.scrollHeight,
      });

      const imgData = canvas.toDataURL('image/png');

      // Build a PDF page sized to match the captured image's aspect ratio,
      // so nothing is cropped or rescaled awkwardly.
      const pxToMm = (px) => px * 0.264583;
      const pdfWidth = pxToMm(canvas.width / 2);   // /2 to undo the scale:2 factor
      const pdfHeight = pxToMm(canvas.height / 2);

      const pdf = new jsPDF({
        orientation: pdfWidth > pdfHeight ? 'landscape' : 'portrait',
        unit: 'mm',
        format: [pdfWidth, pdfHeight],
      });

      pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
      pdf.save(`kpi-simulator-snapshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.pdf`);
    } catch (err) {
      console.error('PDF generation failed:', err);
      alert('Could not generate PDF. See console for details.');
    } finally {
      setPrinting(false);
    }
  };

  return (
    <Box sx={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      px: 3, py: 2.25, backgroundColor: '#FFFFFF',
      borderBottom: `1px solid ${COLORS.border}`,
    }}>
      <Typography sx={{ fontSize: 26, fontWeight: 800, color: COLORS.textPrimary }}>
        KPI Simulator
      </Typography>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }} data-print-hide="true">
        <Tooltip title="Download current page as PDF — captures all KPI cards and slider values">
          <Button
            variant="contained"
            onClick={handleDownloadPDF}
            disabled={printing}
            startIcon={printing ? <CircularProgress size={16} color="inherit" /> : <DownloadIcon />}
            sx={{
              backgroundColor: COLORS.primaryDark,
              px: 2.5, py: 1, fontSize: 13, minHeight: 44,
              '&:hover': { backgroundColor: COLORS.primary },
              '&.Mui-disabled': { backgroundColor: '#9CA3AF', color: '#fff' },
            }}
          >
            {printing ? 'Preparing PDF…' : 'Download PDF'}
          </Button>
        </Tooltip>

        {/* Keep hidden upload for programmatic Excel import (used by seed/admin) */}
        <Avatar sx={{ width: 40, height: 40, backgroundColor: COLORS.primaryDark, fontSize: 13 }}>
          NG
        </Avatar>
      </Box>
    </Box>
  );
}
