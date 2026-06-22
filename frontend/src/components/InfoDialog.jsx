import { Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button, List, ListItem, ListItemText } from '@mui/material';
import { COLORS } from '../theme/theme';

export default function InfoDialog({ open, title, description, bullets, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700, color: COLORS.textPrimary }}>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: bullets?.length ? 1.5 : 0 }}>{description}</DialogContentText>
        {bullets?.length > 0 && (
          <List dense sx={{ pl: 1 }}>
            {bullets.map((b, i) => (
              <ListItem key={i} sx={{ display: 'list-item', listStyleType: 'disc', pl: 0 }}>
                <ListItemText primary={b} />
              </ListItem>
            ))}
          </List>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button
          variant="contained"
          onClick={onClose}
          sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          Got it
        </Button>
      </DialogActions>
    </Dialog>
  );
}
